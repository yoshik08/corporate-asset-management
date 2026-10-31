"""Maintenance prediction for the Corporate Asset Management System.

Approach
--------
A ridge regression (implemented with numpy, no sklearn needed) is trained
on the asset's own maintenance history:

* one training sample per pair of consecutive maintenance events
* features: asset age in days, days since previous maintenance,
  maintenance count so far, and the asset category (one-hot, laptop baseline)
* target: days from this maintenance to the next one

The trained model predicts the interval to the next maintenance for every
asset, which gives a predicted next-maintenance date. A risk score
(0-100) and risk level are derived from days remaining, asset condition,
age and usage hours.

If there are too few training samples (< 8) the predictor falls back to
the median observed interval per category, so it still works on a fresh
database with little history.
"""
from datetime import date, timedelta

import numpy as np

CATEGORIES = ["laptop", "phone", "vehicle", "equipment"]
# Fallback intervals (days) per category, used when history is too thin.
FALLBACK_INTERVAL = {"laptop": 90, "phone": 120, "vehicle": 60, "equipment": 180}
LAMBDA = 10.0  # ridge penalty


def _parse(d):
    return date.fromisoformat(d) if isinstance(d, str) else d


def build_training_data(conn):
    """Return (X, y, meta) from maintenance history.

    X rows: [age_days, days_since_prev, maint_count, is_phone, is_vehicle,
             is_equipment]; y: days until the next maintenance.
    """
    assets = conn.execute(
        "SELECT id, category, purchase_date FROM assets"
    ).fetchall()
    X, y = [], []
    for asset in assets:
        events = conn.execute(
            "SELECT maintenance_date FROM maintenance WHERE asset_id = ?"
            " ORDER BY maintenance_date",
            (asset["id"],),
        ).fetchall()
        dates = [_parse(e["maintenance_date"]) for e in events]
        purchase = _parse(asset["purchase_date"])
        cat = asset["category"]
        for k, d in enumerate(dates):
            if k + 1 >= len(dates):
                continue  # last event has no "next" to learn from
            prev = dates[k - 1] if k > 0 else purchase
            age_days = (d - purchase).days
            since_prev = (d - prev).days
            target = (dates[k + 1] - d).days
            if target <= 0 or since_prev <= 0:
                continue
            X.append([
                float(age_days),
                float(since_prev),
                float(k),
                1.0 if cat == "phone" else 0.0,
                1.0 if cat == "vehicle" else 0.0,
                1.0 if cat == "equipment" else 0.0,
            ])
            y.append(float(target))
    return np.array(X, dtype=float), np.array(y, dtype=float)


def train_model(conn):
    """Train the ridge model. Returns a dict describing the model."""
    X, y = build_training_data(conn)
    if len(y) < 8:
        return {"method": "fallback_median", "samples": int(len(y)), "mae": None,
                "coef": None, "fallback": FALLBACK_INTERVAL}
    # Standardise features (store mean/std for prediction time).
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1.0
    Xs = (X - mean) / std
    # Ridge: add intercept column, penalise everything except the intercept.
    Xd = np.hstack([np.ones((len(Xs), 1)), Xs])
    p = Xd.shape[1]
    penalty = np.eye(p) * LAMBDA
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(Xd.T @ Xd + penalty, Xd.T @ y)
    preds = Xd @ coef
    mae = float(np.mean(np.abs(preds - y)))
    return {"method": "ridge_regression", "samples": int(len(y)), "mae": mae,
            "coef": coef.tolist(), "mean": mean.tolist(), "std": std.tolist(),
            "fallback": FALLBACK_INTERVAL}


def _predict_interval(model, age_days, since_prev, maint_count, category):
    if model["method"] == "fallback_median":
        return float(model["fallback"].get(category, 90))
    coef = np.array(model["coef"])
    mean = np.array(model["mean"])
    std = np.array(model["std"])
    feats = np.array([
        float(age_days), float(since_prev), float(maint_count),
        1.0 if category == "phone" else 0.0,
        1.0 if category == "vehicle" else 0.0,
        1.0 if category == "equipment" else 0.0,
    ])
    xs = (feats - mean) / std
    xd = np.concatenate([[1.0], xs])
    interval = float(xd @ coef)
    return max(7.0, min(365.0, interval))


def _risk_score(days_remaining, condition, age_days, usage_hours):
    """0-100. Higher = needs attention sooner."""
    if days_remaining is None:
        return 50
    if days_remaining < 0:
        score = 90 + min(10, -days_remaining // 3)
    elif days_remaining <= 14:
        score = 75 + (14 - days_remaining)
    elif days_remaining <= 45:
        score = 50 + (45 - days_remaining) * 0.7
    elif days_remaining <= 90:
        score = 25 + (90 - days_remaining) * 0.5
    else:
        score = max(5, 25 - (days_remaining - 90) * 0.05)
    if condition == "poor":
        score += 10
    elif condition == "fair":
        score += 5
    if age_days > 1095:  # 3+ years old
        score += 5
    if usage_hours and usage_hours > 5000:
        score += 5
    return int(max(0, min(100, round(score))))


def predict_all(conn, today=None):
    """Predict next maintenance for every non-retired asset.

    Returns (predictions, model_info).
    """
    today = today or date.today()
    model = train_model(conn)
    assets = conn.execute(
        "SELECT * FROM assets WHERE status != 'retired' ORDER BY id"
    ).fetchall()
    predictions = []
    for a in assets:
        events = conn.execute(
            "SELECT maintenance_date FROM maintenance WHERE asset_id = ?"
            " ORDER BY maintenance_date DESC LIMIT 1",
            (a["id"],),
        ).fetchone()
        maint_count = conn.execute(
            "SELECT COUNT(*) AS c FROM maintenance WHERE asset_id = ?",
            (a["id"],),
        ).fetchone()["c"]
        purchase = _parse(a["purchase_date"])
        age_days = (today - purchase).days
        if events:
            last_maint = _parse(events["maintenance_date"])
            since_prev = (today - last_maint).days
            base_date = last_maint
        else:
            since_prev = age_days
            base_date = purchase
        interval = _predict_interval(
            model, age_days, since_prev, maint_count, a["category"])
        next_due = base_date + timedelta(days=int(round(interval)))
        days_remaining = (next_due - today).days
        score = _risk_score(days_remaining, a["condition"], age_days,
                            a["usage_hours"])
        level = "high" if score >= 70 else ("medium" if score >= 40 else "low")
        predictions.append({
            "asset_id": a["id"],
            "asset_tag": a["asset_tag"],
            "name": a["name"],
            "category": a["category"],
            "status": a["status"],
            "condition": a["condition"],
            "last_maintenance_date": (events["maintenance_date"]
                                      if events else None),
            "maintenance_count": maint_count,
            "predicted_interval_days": int(round(interval)),
            "predicted_next_maintenance": next_due.isoformat(),
            "days_remaining": days_remaining,
            "risk_score": score,
            "risk_level": level,
        })
    predictions.sort(key=lambda p: (p["days_remaining"] is None,
                                    p["days_remaining"]))
    model_info = {
        "method": model["method"],
        "training_samples": model["samples"],
        "training_mae_days": (round(model["mae"], 1)
                              if model.get("mae") is not None else None),
    }
    return predictions, model_info
