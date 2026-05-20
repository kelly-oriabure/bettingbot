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
import uuid
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


def split_train_test(df: pd.DataFrame, test_fraction: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split historical data before fitting so backtests avoid leakage."""
    if df.empty:
        raise ValueError("Cannot split empty training data")

    ordered = df.sort_values("date") if "date" in df.columns else df.copy()
    ordered = ordered.reset_index(drop=True)
    split_index = int(len(ordered) * (1 - test_fraction))
    split_index = min(max(split_index, 1), len(ordered))
    train_df = ordered.iloc[:split_index].copy()
    test_df = ordered.iloc[split_index:].copy()
    return train_df, test_df


def train_dixon_coles(df: pd.DataFrame, artifact_path: str = "data/model.json", model_cls=None):
    """Train Dixon-Coles Poisson model."""
    if model_cls is None:
        from app.models.dixon_coles import DixonColesModel

        model_cls = DixonColesModel
    
    logger.info("Training Dixon-Coles model...")
    model = model_cls(max_goals=7)
    model.fit(df)
    
    # Save parameters
    artifact_dir = os.path.dirname(artifact_path)
    if artifact_dir:
        os.makedirs(artifact_dir, exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump(model.params, f, indent=2)
    
    logger.info(f"Dixon-Coles model saved. {len(model.teams)} teams, {len(model.params)} params")
    return model


def evaluate_model(model, test_df: pd.DataFrame) -> dict:
    """Evaluate model accuracy on held-out test data."""
    correct = 0
    total = 0
    score_correct = 0
    ou_correct = 0
    btts_correct = 0
    unavailable = 0
    
    for _, row in test_df.iterrows():
        pred = model.predict_match(row['home_team'], row['away_team'])
        if pred is None:
            unavailable += 1
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
        "total_test_matches": len(test_df),
        "evaluated_predictions": total,
        "unavailable_predictions": unavailable,
        "match_outcome_accuracy": round(correct / max(total, 1), 4),
        "correct_score_accuracy": round(score_correct / max(total, 1), 4),
        "over_under_accuracy": round(ou_correct / max(total, 1), 4),
        "btts_accuracy": round(btts_correct / max(total, 1), 4),
        "market_metrics": {
            "1x2": {
                "sample_size": total,
                "correct": correct,
                "hit_rate": round(correct / max(total, 1), 4),
            },
            "over_under_2_5": {
                "sample_size": total,
                "correct": ou_correct,
                "hit_rate": round(ou_correct / max(total, 1), 4),
            },
            "btts": {
                "sample_size": total,
                "correct": btts_correct,
                "hit_rate": round(btts_correct / max(total, 1), 4),
            },
        },
        "evaluated_at": datetime.utcnow().isoformat(),
    }
    
    logger.info(f"Evaluation results: {json.dumps(results, indent=2)}")
    return results


def store_model_version(
    metrics: dict,
    artifact_path: str,
    league_ids: list,
    seasons: list,
    train_df: pd.DataFrame,
    db_path: str = None,
) -> str:
    """Store model version metadata for traceability."""
    from app.data.storage import dumps_payload, initialize_database, session

    initialize_database(db_path)
    version = f"dixon_coles-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    trained_from = None
    trained_to = None
    if "date" in train_df.columns and not train_df.empty:
        trained_from = str(train_df["date"].min())
        trained_to = str(train_df["date"].max())

    model_metrics = dict(metrics)
    model_metrics["leagues"] = league_ids
    model_metrics["seasons"] = seasons
    model_metrics["training_sample_size"] = len(train_df)

    with session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO model_versions (
                version, model_type, trained_from, trained_to, metrics, artifact_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                version,
                "dixon_coles",
                trained_from,
                trained_to,
                dumps_payload(model_metrics),
                artifact_path,
            ),
        )

    return version


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
    parser.add_argument("--db-path", default=None,
                        help="Optional SQLite path for model version metadata")
    args = parser.parse_args()
    
    league_ids = [int(x) for x in args.leagues.split(",")]
    seasons = [int(x) for x in args.seasons.split(",")]
    
    # 1. Fetch data
    df = await fetch_data(league_ids, seasons)
    
    # Save raw data
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/training_data.csv", index=False)
    logger.info(f"Training data saved to data/training_data.csv")

    train_df, test_df = split_train_test(df)
    logger.info(f"Train/test split: {len(train_df)} train, {len(test_df)} test")
    
    # 2. Train Dixon-Coles
    artifact_path = "data/model.json"
    dc_model = train_dixon_coles(train_df, artifact_path=artifact_path)
    
    # 3. Evaluate
    results = evaluate_model(dc_model, test_df)
    
    # 4. Train XGBoost (if available)
    try:
        xgb_model = train_xgboost(train_df)
    except Exception as e:
        logger.warning(f"XGBoost training failed (may not be installed): {e}")
        xgb_model = None
    
    # 5. Save evaluation report
    results["leagues"] = league_ids
    results["seasons"] = seasons
    results["total_matches"] = len(df)
    results["training_matches"] = len(train_df)
    results["model_version"] = store_model_version(
        results,
        artifact_path=artifact_path,
        league_ids=league_ids,
        seasons=seasons,
        train_df=train_df,
        db_path=args.db_path,
    )
    
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
