"""
Dixon-Coles Poisson Model for football score prediction.

The classic model: estimates attack/defense strength per team,
calculates expected goals (λ) for each side, then generates
a full probability matrix of possible scores.

Reference: Dixon & Coles (1997) "Modelling Association Football Scores
and Inefficiencies in the Football Betting Market"
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class MatchPrediction:
    """Structured prediction for a single match."""
    home_team: str
    away_team: str
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    expected_home_goals: float
    expected_away_goals: float
    top_scores: List[Tuple[str, float]]  # (score_str, probability)
    over_under_25: float  # probability of over 2.5 goals
    btts_prob: float  # both teams to score probability
    confidence: str  # "high", "medium", "low"


class DixonColesModel:
    """
    Dixon-Coles model for predicting football match scores.
    
    Key concepts:
    - Each team has an attack parameter (α) and defense parameter (β)
    - Home advantage is modeled as a separate parameter (γ)
    - Low-scoring outcomes (0-0, 1-0, 0-1, 1-1) are corrected with τ parameter
    - Uses maximum likelihood estimation to fit parameters
    """

    # Correction factor for low-scoring results
    TAU_CORRECTIONS = {
        (0, 0): 1.0,   # will be estimated
        (1, 0): 1.0,
        (0, 1): 1.0,
        (1, 1): 1.0,
    }

    def __init__(self, max_goals: int = 7):
        self.max_goals = max_goals
        self.params: Dict[str, float] = {}
        self.teams: List[str] = []
        self.fitted = False

    def _tau(self, x: int, y: int, lambda_: float, mu: float, rho: float) -> float:
        """
        Dixon-Coles correction factor for low-scoring outcomes.
        Adjusts probabilities for 0-0, 1-0, 0-1, 1-1 scores.
        """
        if x == 0 and y == 0:
            return 1 - lambda_ * mu * rho
        elif x == 0 and y == 1:
            return 1 + lambda_ * rho
        elif x == 1 and y == 0:
            return 1 + mu * rho
        elif x == 1 and y == 1:
            return 1 - rho
        else:
            return 1.0

    def _match_log_likelihood(
        self, params: np.ndarray, data: pd.DataFrame,
        teams: List[str], rho: float
    ) -> float:
        """Calculate log-likelihood for all matches (vectorized)."""
        team_idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        
        attack = params[:n]
        defense = params[n:2*n]
        home_adv = params[2*n]
        
        # Vectorized lookup
        home_idx = np.array([team_idx[t] for t in data['home_team']], dtype=np.int32)
        away_idx = np.array([team_idx[t] for t in data['away_team']], dtype=np.int32)
        hg = data['home_goals'].values.astype(np.float64)
        ag = data['away_goals'].values.astype(np.float64)
        
        # Expected goals (vectorized)
        lambda_ = np.exp(attack[home_idx] + defense[away_idx] + home_adv)
        mu = np.exp(attack[away_idx] + defense[home_idx])
        
        # Clamp for numerical stability
        lambda_ = np.maximum(lambda_, 0.01)
        mu = np.maximum(mu, 0.01)
        
        # Poisson log-likelihood (vectorized)
        log_lik = poisson.logpmf(hg, lambda_) + poisson.logpmf(ag, mu)
        
        # Dixon-Coles tau correction (vectorized)
        tau = np.ones_like(log_lik)
        mask_00 = (hg == 0) & (ag == 0)
        mask_10 = (hg == 1) & (ag == 0)
        mask_01 = (hg == 0) & (ag == 1)
        mask_11 = (hg == 1) & (ag == 1)
        
        tau[mask_00] = 1 - lambda_[mask_00] * mu[mask_00] * rho
        tau[mask_10] = 1 + lambda_[mask_10] * rho
        tau[mask_01] = 1 + mu[mask_01] * rho
        tau[mask_11] = 1 - rho
        
        tau = np.maximum(tau, 1e-10)
        log_lik += np.log(tau)
        
        return -np.sum(log_lik)

    def fit(self, data: pd.DataFrame, rho_init: float = -0.13) -> None:
        """
        Fit the Dixon-Coles model to historical match data.
        
        Args:
            data: DataFrame with columns [home_team, away_team, home_goals, away_goals]
            rho_init: Initial value for correlation parameter
        """
        self.teams = sorted(set(data['home_team'].tolist() + data['away_team'].tolist()))
        n = len(self.teams)
        
        logger.info(f"Fitting Dixon-Coles model on {len(data)} matches, {n} teams")
        
        # Initial parameters: all zeros (attack=0, defense=0, home_adv=0.3)
        x0 = np.zeros(2 * n + 1)
        x0[2 * n] = 0.3  # initial home advantage
        
        # Bounds: defense parameters can be negative, attack can be negative
        bounds = [(-3, 3)] * (2 * n) + [(0, 2)]  # home advantage positive
        
        result = minimize(
            self._match_log_likelihood,
            x0,
            args=(data, self.teams, rho_init),
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': 300, 'ftol': 1e-6}
        )
        
        if not result.success:
            logger.warning(f"Optimization warning: {result.message}")
        
        # Store fitted parameters
        self.params = {}
        for i, team in enumerate(self.teams):
            self.params[f'attack_{team}'] = result.x[i]
            self.params[f'defense_{team}'] = result.x[n + i]
        self.params['home_advantage'] = result.x[2 * n]
        self.params['rho'] = rho_init
        
        self.fitted = True
        logger.info(f"Model fitted. Home advantage: {result.x[2*n]:.4f}")

    def predict_match(
        self, home_team: str, away_team: str
    ) -> Optional[MatchPrediction]:
        """
        Predict a single match outcome.
        
        Returns full probability breakdown including correct scores.
        """
        if not self.fitted:
            logger.error("Model not fitted yet!")
            return None
        
        if home_team not in self.teams or away_team not in self.teams:
            logger.warning(f"Unknown team: {home_team} or {away_team}")
            return None
        
        attack_h = self.params[f'attack_{home_team}']
        defense_h = self.params[f'defense_{home_team}']
        attack_a = self.params[f'attack_{away_team}']
        defense_a = self.params[f'defense_{away_team}']
        home_adv = self.params['home_advantage']
        rho = self.params.get('rho', -0.13)
        
        # Expected goals
        lambda_ = np.exp(attack_h + defense_a + home_adv)
        mu = np.exp(attack_a + defense_h)
        
        # Clamp
        lambda_ = max(lambda_, 0.3)
        mu = max(mu, 0.3)
        
        # Build score probability matrix
        score_probs = {}
        home_win_prob = 0.0
        draw_prob = 0.0
        away_win_prob = 0.0
        over_25 = 0.0
        btts = 0.0
        
        for i in range(self.max_goals + 1):
            for j in range(self.max_goals + 1):
                tau = self._tau(i, j, lambda_, mu, rho)
                prob = tau * poisson.pmf(i, lambda_) * poisson.pmf(j, mu)
                score_key = f"{i}-{j}"
                score_probs[score_key] = prob
                
                if i > j:
                    home_win_prob += prob
                elif i == j:
                    draw_prob += prob
                else:
                    away_win_prob += prob
                
                if i + j > 2.5:
                    over_25 += prob
                if i > 0 and j > 0:
                    btts += prob
        
        # Normalize (should already sum to ~1)
        total = home_win_prob + draw_prob + away_win_prob
        home_win_prob /= total
        draw_prob /= total
        away_win_prob /= total
        
        # Top 5 most likely scores
        top_scores = sorted(score_probs.items(), key=lambda x: -x[1])[:5]
        top_scores = [(k, v) for k, v in top_scores]
        
        # Confidence based on entropy of outcome distribution
        probs = [home_win_prob, draw_prob, away_win_prob]
        entropy = -sum(p * np.log2(p + 1e-10) for p in probs)
        max_entropy = np.log2(3)
        certainty = 1 - entropy / max_entropy
        
        if certainty > 0.5:
            confidence = "high"
        elif certainty > 0.25:
            confidence = "medium"
        else:
            confidence = "low"
        
        return MatchPrediction(
            home_team=home_team,
            away_team=away_team,
            home_win_prob=home_win_prob,
            draw_prob=draw_prob,
            away_win_prob=away_win_prob,
            expected_home_goals=round(lambda_, 2),
            expected_away_goals=round(mu, 2),
            top_scores=top_scores,
            over_under_25=round(over_25, 4),
            btts_prob=round(btts, 4),
            confidence=confidence,
        )

    def get_team_strength(self, team: str) -> Dict[str, float]:
        """Get a team's attack and defense ratings."""
        if team not in self.teams:
            return {}
        return {
            'attack': round(self.params[f'attack_{team}'], 4),
            'defense': round(self.params[f'defense_{team}'], 4),
        }
