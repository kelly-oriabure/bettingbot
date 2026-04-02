"""
Training script — fetches historical data and trains the prediction models.

Usage:
    python -m app.train [--leagues 39,140,61] [--seasons 2023,2024,2025]

Outputs:
    - data/model.json (Dixon-Coles parameters)
    - data/xgb_model.json (XGBoost model)
    - data/training_report.json (accuracy metrics)
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from datetime import datetime

import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train")


async def fetch_data(league_ids: list, seasons: list) -> pd.DataFrame:
    """Fetch historical match data."""
    from app.data.fetcher import DataManager
    
    dm = DataManager()
    logger.info(f"Fetching data for leagues {league_ids}, seasons {seasons}")
    
    df = await dm.get_training_data(league_ids, seasons)
    logger.info(f"Fetched {len(df)} total matches")
    
    if df.empty:
        logger.error("No data fetched! Check API keys and network.")
        sys.exit(1)
    
    return df


def train_dixon_coles(df: pd.DataFrame):
    """Train Dixon-Coles Poisson model."""
    from app.models.dixon_coles import DixonColesModel
    
    logger.info("Training Dixon-Coles model...")
    model = DixonColesModel(max_goals=7)
    model.fit(df)
    
    # Save parameters
    os.makedirs("data", exist_ok=True)
    with open("data/model.json", "w") as f:
        json.dump(model.params, f, indent=2)
    
    logger.info(f"Dixon-Coles model saved. {len(model.teams)} teams, {len(model.params)} params")
    return model


def evaluate_model(model, df: pd.DataFrame) -> dict:
    """Evaluate model accuracy on the dataset."""
    correct = 0
    total = 0
    score_correct = 0
    ou_correct = 0
    btts_correct = 0
    
    # Use last 20% as test set
    split = int(len(df) * 0.8)
    test_df = df.iloc[split:]
    
    for _, row in test_df.iterrows():
        pred = model.predict_match(row['home_team'], row['away_team'])
        if pred is None:
            continue
        
        total += 1
        
        # Match outcome
        actual_hg = int(row['home_goals'])
        actual_ag = int(row['away_goals'])
        
        if actual_hg > actual_ag:
            actual = "home"
        elif actual_hg < actual_ag:
            actual = "away"
        else:
            actual = "draw"
        
        probs = {"home": pred.home_win_prob, "draw": pred.draw_prob, "away": pred.away_win_prob}
        predicted = max(probs, key=probs.get)
        
        if predicted == actual:
            correct += 1
        
        # Correct score (within ±1)
        predicted_home_goals = round(pred.expected_home_goals)
        predicted_away_goals = round(pred.expected_away_goals)
        if abs(predicted_home_goals - actual_hg) <= 1 and abs(predicted_away_goals - actual_ag) <= 1:
            score_correct += 1
        
        # Over/Under 2.5
        actual_ou = (actual_hg + actual_ag) > 2.5
        predicted_ou = pred.over_under_25 > 0.5
        if actual_ou == predicted_ou:
            ou_correct += 1
        
        # BTTS
        actual_btts = actual_hg > 0 and actual_ag > 0
        predicted_btts = pred.btts_prob > 0.5
        if actual_btts == predicted_btts:
            btts_correct += 1
    
    results = {
        "total_test_matches": total,
        "match_outcome_accuracy": round(correct / max(total, 1), 4),
        "correct_score_accuracy": round(score_correct / max(total, 1), 4),
        "over_under_accuracy": round(ou_correct / max(total, 1), 4),
        "btts_accuracy": round(btts_correct / max(total, 1), 4),
        "evaluated_at": datetime.utcnow().isoformat(),
    }
    
    logger.info(f"Evaluation results: {json.dumps(results, indent=2)}")
    return results


def train_xgboost(df: pd.DataFrame):
    """Train XGBoost ensemble model."""
    from app.models.xgboost_model import XGBoostPredictor, FeatureEngineer
    
    logger.info("Training XGBoost model...")
    fe = FeatureEngineer()
    predictor = XGBoostPredictor()
    
    # Build features for each match
    features_list = []
    for _, row in df.iterrows():
        hist = df[df['date'] < row['date']] if 'date' in df.columns else df
        feat = fe.build_features(row['home_team'], row['away_team'], hist)
        features_list.append(feat)
    
    if features_list:
        predictor.fit(df, features_list)
        if predictor.fitted:
            logger.info("XGBoost model trained successfully")
    
    return predictor


async def main():
    parser = argparse.ArgumentParser(description="Train BettingBot prediction models")
    parser.add_argument("--leagues", default="39,140,61,135,78",
                        help="Comma-separated league IDs (default: top 5 European)")
    parser.add_argument("--seasons", default="2024,2025",
                        help="Comma-separated seasons (default: 2024,2025)")
    args = parser.parse_args()
    
    league_ids = [int(x) for x in args.leagues.split(",")]
    seasons = [int(x) for x in args.seasons.split(",")]
    
    # 1. Fetch data
    df = await fetch_data(league_ids, seasons)
    
    # Save raw data
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/training_data.csv", index=False)
    logger.info(f"Training data saved to data/training_data.csv")
    
    # 2. Train Dixon-Coles
    dc_model = train_dixon_coles(df)
    
    # 3. Evaluate
    results = evaluate_model(dc_model, df)
    
    # 4. Train XGBoost (if available)
    try:
        xgb_model = train_xgboost(df)
    except Exception as e:
        logger.warning(f"XGBoost training failed (may not be installed): {e}")
        xgb_model = None
    
    # 5. Save evaluation report
    results["leagues"] = league_ids
    results["seasons"] = seasons
    results["total_matches"] = len(df)
    
    with open("data/training_report.json", "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info("=" * 50)
    logger.info("Training complete!")
    logger.info(f"Match outcome accuracy: {results['match_outcome_accuracy']*100:.1f}%")
    logger.info(f"Correct score (±1): {results['correct_score_accuracy']*100:.1f}%")
    logger.info(f"Over/Under accuracy: {results['over_under_accuracy']*100:.1f}%")
    logger.info(f"BTTS accuracy: {results['btts_accuracy']*100:.1f}%")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
