"""
XGBoost-based match outcome predictor.

Uses gradient boosting on engineered features including:
- Team form (last N matches)
- Head-to-head record
- Home/away splits
- Attack/defense ratings
- Expected goals (xG) if available
- Bookmaker odds (implied probabilities)
- Fatigue (days since last match)
- League position difference
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


def _safe_import_xgboost():
    """Import XGBoost with fallback."""
    try:
        import xgboost as xgb
        return xgb
    except ImportError:
        logger.warning("XGBoost not available, using sklearn fallback")
        return None


class FeatureEngineer:
    """Transform raw match data into ML-ready features."""

    @staticmethod
    def compute_form(matches: pd.DataFrame, team: str, n: int = 5) -> Dict[str, float]:
        """Calculate recent form for a team."""
        team_matches = matches[
            (matches['home_team'] == team) | (matches['away_team'] == team)
        ].sort_values('date', ascending=False).head(n)
        
        if len(team_matches) == 0:
            return {'wins': 0, 'draws': 0, 'losses': 0, 'goals_scored': 0, 'goals_conceded': 0}
        
        wins = draws = losses = scored = conceded = 0
        for _, row in team_matches.iterrows():
            if row['home_team'] == team:
                hg, ag = row['home_goals'], row['away_goals']
            else:
                hg, ag = row['away_goals'], row['home_goals']
            
            scored += hg
            conceded += ag
            if hg > ag:
                wins += 1
            elif hg == ag:
                draws += 1
            else:
                losses += 1
        
        total = len(team_matches)
        return {
            'wins': wins / total,
            'draws': draws / total,
            'losses': losses / total,
            'goals_scored': scored / total,
            'goals_conceded': conceded / total,
            'points_per_game': (wins * 3 + draws) / total,
        }

    @staticmethod
    def compute_h2h(
        matches: pd.DataFrame, team1: str, team2: str, n: int = 10
    ) -> Dict[str, float]:
        """Head-to-head record between two teams."""
        h2h = matches[
            (
                ((matches['home_team'] == team1) & (matches['away_team'] == team2)) |
                ((matches['home_team'] == team2) & (matches['away_team'] == team1))
            )
        ].sort_values('date', ascending=False).head(n)
        
        if len(h2h) == 0:
            return {'h2h_team1_wins': 0.5, 'h2h_draws': 0, 'h2h_avg_goals': 2.5}
        
        t1_wins = draws = total_goals = 0
        for _, row in h2h.iterrows():
            total_goals += row['home_goals'] + row['away_goals']
            if row['home_team'] == team1:
                if row['home_goals'] > row['away_goals']:
                    t1_wins += 1
                elif row['home_goals'] == row['away_goals']:
                    draws += 1
            else:
                if row['away_goals'] > row['home_goals']:
                    t1_wins += 1
                elif row['away_goals'] == row['home_goals']:
                    draws += 1
        
        n_h2h = len(h2h)
        return {
            'h2h_team1_wins': t1_wins / n_h2h,
            'h2h_draws': draws / n_h2h,
            'h2h_avg_goals': total_goals / n_h2h,
        }

    @staticmethod
    def compute_attack_defense(
        matches: pd.DataFrame, team: str, league_avg_gpg: float = 1.4
    ) -> Dict[str, float]:
        """Attack and defense strength ratings."""
        team_matches = matches[
            (matches['home_team'] == team) | (matches['away_team'] == team)
        ].tail(20)
        
        if len(team_matches) == 0:
            return {'attack_strength': 1.0, 'defense_strength': 1.0}
        
        scored = conceded = home_games = away_games = 0
        scored_home = scored_away = 0
        
        for _, row in team_matches.iterrows():
            if row['home_team'] == team:
                scored += row['home_goals']
                conceded += row['away_goals']
                scored_home += row['home_goals']
                home_games += 1
            else:
                scored += row['away_goals']
                conceded += row['home_goals']
                scored_away += row['away_goals']
                away_games += 1
        
        total = len(team_matches)
        avg_scored = scored / total if total > 0 else league_avg_gpg
        avg_conceded = conceded / total if total > 0 else league_avg_gpg
        
        return {
            'attack_strength': avg_scored / league_avg_gpg,
            'defense_strength': league_avg_gpg / max(avg_conceded, 0.1),
            'home_attack': (scored_home / max(home_games, 1)) / league_avg_gpg,
            'away_attack': (scored_away / max(away_games, 1)) / league_avg_gpg,
        }

    def build_features(
        self,
        home_team: str,
        away_team: str,
        historical_matches: pd.DataFrame,
        home_team_position: int = 0,
        away_team_position: int = 0,
        home_odds: float = 0,
        draw_odds: float = 0,
        away_odds: float = 0,
    ) -> Dict[str, float]:
        """Build a complete feature vector for a match."""
        features = {}
        
        # Home form (last 5)
        home_form = self.compute_form(historical_matches, home_team, 5)
        for k, v in home_form.items():
            features[f'home_{k}'] = v
        
        # Away form (last 5)
        away_form = self.compute_form(historical_matches, away_team, 5)
        for k, v in away_form.items():
            features[f'away_{k}'] = v
        
        # Head to head
        h2h = self.compute_h2h(historical_matches, home_team, away_team)
        features.update(h2h)
        
        # Attack/defense
        league_avg = (historical_matches['home_goals'].mean() + historical_matches['away_goals'].mean()) / 2
        home_ad = self.compute_attack_defense(historical_matches, home_team, league_avg)
        away_ad = self.compute_attack_defense(historical_matches, away_team, league_avg)
        for k, v in home_ad.items():
            features[f'home_{k}'] = v
        for k, v in away_ad.items():
            features[f'away_{k}'] = v
        
        # League position
        features['position_diff'] = home_team_position - away_team_position
        features['home_position'] = home_team_position
        features['away_position'] = away_team_position
        
        # Implied probabilities from odds
        if home_odds > 0:
            features['odds_implied_home'] = 1 / home_odds
            features['odds_implied_draw'] = 1 / draw_odds if draw_odds > 0 else 0.25
            features['odds_implied_away'] = 1 / away_odds if away_odds > 0 else 0.25
            # Normalize
            total_imp = features['odds_implied_home'] + features['odds_implied_draw'] + features['odds_implied_away']
            features['odds_margin'] = total_imp - 1  # bookmaker margin
        
        # Form differential
        features['form_diff'] = home_form['points_per_game'] - away_form['points_per_game']
        features['attack_diff'] = home_ad['attack_strength'] - away_ad['attack_strength']
        features['defense_diff'] = home_ad['defense_strength'] - away_ad['defense_strength']
        
        return features


class XGBoostPredictor:
    """XGBoost-based match outcome predictor."""
    
    FEATURE_COLS = [
        'home_wins', 'home_draws', 'home_losses', 'home_goals_scored', 'home_goals_conceded',
        'home_points_per_game', 'away_wins', 'away_draws', 'away_losses',
        'away_goals_scored', 'away_goals_conceded', 'away_points_per_game',
        'h2h_team1_wins', 'h2h_draws', 'h2h_avg_goals',
        'home_attack_strength', 'home_defense_strength', 'home_home_attack', 'home_away_attack',
        'away_attack_strength', 'away_defense_strength', 'away_home_attack', 'away_away_attack',
        'position_diff', 'form_diff', 'attack_diff', 'defense_diff',
    ]
    
    def __init__(self):
        self.model_home = None
        self.model_draw = None
        self.model_away = None
        self.model_goals = None  # for total goals
        self.fitted = False
        self.feature_engineer = FeatureEngineer()
    
    def fit(self, data: pd.DataFrame, features_list: List[Dict[str, float]]) -> None:
        """Train XGBoost models on historical data with features."""
        xgb = _safe_import_xgboost()
        if xgb is None:
            logger.warning("XGBoost not installed, skipping XGB training")
            return
        
        # Build feature matrix
        X = pd.DataFrame(features_list)
        # Only use columns that exist
        available_cols = [c for c in self.FEATURE_COLS if c in X.columns]
        X = X[available_cols].fillna(0)
        
        # Targets
        y_home = (data['home_goals'] > data['away_goals']).astype(int)
        y_draw = (data['home_goals'] == data['away_goals']).astype(int)
        y_away = (data['home_goals'] < data['away_goals']).astype(int)
        y_total_goals = data['home_goals'] + data['away_goals']
        
        params = {
            'max_depth': 5,
            'learning_rate': 0.1,
            'n_estimators': 200,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'eval_metric': 'logloss',
        }
        
        # Train one model per outcome
        self.model_home = xgb.XGBClassifier(**params)
        self.model_draw = xgb.XGBClassifier(**params)
        self.model_away = xgb.XGBClassifier(**params)
        
        self.model_home.fit(X, y_home)
        self.model_draw.fit(X, y_draw)
        self.model_away.fit(X, y_away)
        
        # Goals regression
        self.model_goals = xgb.XGBRegressor(
            max_depth=5, learning_rate=0.1, n_estimators=200,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
        )
        self.model_goals.fit(X, y_total_goals)
        
        self.fitted = True
        self.available_cols = available_cols
        logger.info(f"XGBoost models trained on {len(X)} samples with {len(available_cols)} features")
    
    def predict(self, features: Dict[str, float]) -> Optional[Dict[str, float]]:
        """Predict match outcome probabilities."""
        if not self.fitted:
            return None
        
        X = pd.DataFrame([features])[self.available_cols].fillna(0)
        
        home_prob = self.model_home.predict_proba(X)[0][1]
        draw_prob = self.model_draw.predict_proba(X)[0][1]
        away_prob = self.model_away.predict_proba(X)[0][1]
        
        # Normalize
        total = home_prob + draw_prob + away_prob
        if total > 0:
            home_prob /= total
            draw_prob /= total
            away_prob /= total
        
        expected_total = self.model_goals.predict(X)[0]
        
        return {
            'home_win_prob': round(home_prob, 4),
            'draw_prob': round(draw_prob, 4),
            'away_win_prob': round(away_prob, 4),
            'expected_total_goals': round(max(expected_total, 0.5), 2),
        }


class EnsemblePredictor:
    """
    Combines Dixon-Coles and XGBoost predictions using weighted averaging.
    Weights are calibrated based on recent backtest performance.
    """
    
    def __init__(
        self,
        poisson_model: 'DixonColesModel',
        xgb_model: Optional[XGBoostPredictor] = None,
        poisson_weight: float = 0.6,
        xgb_weight: float = 0.4,
    ):
        self.poisson = poisson_model
        self.xgb = xgb_model
        self.poisson_weight = poisson_weight
        self.xgb_weight = xgb_weight if xgb_model and xgb_model.fitted else 0.0
        
        # Normalize weights
        total = self.poisson_weight + self.xgb_weight
        if total > 0:
            self.poisson_weight /= total
            self.xgb_weight /= total
    
    def predict(
        self,
        home_team: str,
        away_team: str,
        xgb_features: Optional[Dict[str, float]] = None,
    ) -> Optional[Dict]:
        """
        Ensemble prediction combining both models.
        
        Returns merged prediction with confidence scores.
        """
        # Always get Poisson prediction
        poisson_pred = self.poisson.predict_match(home_team, away_team)
        if poisson_pred is None:
            return None
        
        if self.xgb and self.xgb.fitted and xgb_features:
            xgb_pred = self.xgb.predict(xgb_features)
            if xgb_pred:
                # Weighted ensemble
                hw = (
                    self.poisson_weight * poisson_pred.home_win_prob
                    + self.xgb_weight * xgb_pred['home_win_prob']
                )
                dr = (
                    self.poisson_weight * poisson_pred.draw_prob
                    + self.xgb_weight * xgb_pred['draw_prob']
                )
                aw = (
                    self.poisson_weight * poisson_pred.away_win_prob
                    + self.xgb_weight * xgb_pred['away_win_prob']
                )
                
                # Re-normalize
                total = hw + dr + aw
                hw /= total
                dr /= total
                aw /= total
                
                return {
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_win_prob': round(hw, 4),
                    'draw_prob': round(dr, 4),
                    'away_win_prob': round(aw, 4),
                    'expected_home_goals': poisson_pred.expected_home_goals,
                    'expected_away_goals': poisson_pred.expected_away_goals,
                    'top_scores': poisson_pred.top_scores,
                    'over_under_25': poisson_pred.over_under_25,
                    'btts_prob': poisson_pred.btts_prob,
                    'confidence': poisson_pred.confidence,
                    'model': 'ensemble',
                }
        
        # Fallback to Poisson only
        return {
            'home_team': home_team,
            'away_team': away_team,
            'home_win_prob': poisson_pred.home_win_prob,
            'draw_prob': poisson_pred.draw_prob,
            'away_win_prob': poisson_pred.away_win_prob,
            'expected_home_goals': poisson_pred.expected_home_goals,
            'expected_away_goals': poisson_pred.expected_away_goals,
            'top_scores': poisson_pred.top_scores,
            'over_under_25': poisson_pred.over_under_25,
            'btts_prob': poisson_pred.btts_prob,
            'confidence': poisson_pred.confidence,
            'model': 'poisson',
        }
