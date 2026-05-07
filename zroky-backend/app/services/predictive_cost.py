"""Predictive cost anomaly detection using time-series forecasting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Call


class PredictiveCostService:
    """Service for forecasting cost anomalies using statistical methods."""

    def __init__(self, forecast_horizon_hours: int = 4) -> None:
        self.forecast_horizon = forecast_horizon_hours
        self.confidence_interval = 0.95

    def get_hourly_cost_data(
        self,
        db: Session,
        project_id: str,
        hours_back: int = 168,  # 1 week default
    ) -> list[dict[str, Any]]:
        """Get hourly cost aggregates for time series analysis."""
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Group by hour and sum costs
        stmt = (
            select(
                func.date_trunc("hour", Call.created_at).label("hour"),
                func.sum(Call.cost_total).label("total_cost"),
                func.count().label("call_count"),
                func.sum(Call.total_tokens).label("total_tokens"),
            )
            .where(
                Call.project_id == project_id,
                Call.created_at >= start_time,
            )
            .group_by(func.date_trunc("hour", Call.created_at))
            .order_by(func.date_trunc("hour", Call.created_at))
        )
        
        result = db.execute(stmt)
        
        hourly_data = []
        for row in result:
            hourly_data.append({
                "hour": row.hour,
                "total_cost": float(row.total_cost or 0),
                "call_count": row.call_count,
                "total_tokens": row.total_tokens or 0,
            })
        
        return hourly_data

    def calculate_ewma(
        self,
        data: list[float],
        span: int = 12,  # 12-hour span for hourly data
    ) -> list[float]:
        """Calculate Exponentially Weighted Moving Average."""
        if not data:
            return []
        
        alpha = 2 / (span + 1)
        ewma = [data[0]]
        
        for i in range(1, len(data)):
            ewma.append(alpha * data[i] + (1 - alpha) * ewma[i - 1])
        
        return ewma

    def detect_trend(
        self,
        data: list[float],
    ) -> dict[str, Any]:
        """Detect trend using simple linear regression."""
        if len(data) < 2:
            return {"slope": 0, "trend": "stable", "r_squared": 0}
        
        x = np.arange(len(data))
        y = np.array(data)
        
        # Linear regression: y = mx + b
        n = len(x)
        m = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x ** 2) - np.sum(x) ** 2)
        b = (np.sum(y) - m * np.sum(x)) / n
        
        # R-squared
        y_pred = m * x + b
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Classify trend
        if abs(m) < np.std(y) * 0.1 / len(data):
            trend = "stable"
        elif m > 0:
            trend = "increasing"
        else:
            trend = "decreasing"
        
        return {
            "slope": float(m),
            "trend": trend,
            "r_squared": float(r_squared),
            "daily_change_rate": float(m * 24),  # Cost change per day
        }

    def forecast_cost(
        self,
        hourly_data: list[dict[str, Any]],
        hours_ahead: int = 4,
    ) -> dict[str, Any]:
        """Forecast future cost using EWMA and trend analysis."""
        
        if len(hourly_data) < 24:  # Need at least 1 day of data
            return {
                "forecast": [],
                "confidence": "low",
                "reason": "Insufficient historical data (need 24+ hours)",
            }
        
        costs = [d["total_cost"] for d in hourly_data]
        
        # Calculate EWMA
        ewma = self.calculate_ewma(costs)
        
        # Detect trend
        trend_info = self.detect_trend(costs)
        
        # Calculate standard deviation of residuals
        residuals = [costs[i] - ewma[i] for i in range(len(costs))]
        std_residual = np.std(residuals[-48:]) if len(residuals) >= 48 else np.std(residuals)
        
        # Forecast using EWMA + trend
        last_ewma = ewma[-1]
        last_hour = hourly_data[-1]["hour"]
        
        forecast = []
        for i in range(1, hours_ahead + 1):
            # EWMA continues
            forecast_value = last_ewma + trend_info["slope"] * i
            
            # Add confidence intervals (95%)
            margin = 1.96 * std_residual * np.sqrt(i)  # Increasing uncertainty
            
            forecast_hour = last_hour + timedelta(hours=i)
            forecast.append({
                "hour": forecast_hour.isoformat(),
                "predicted_cost": max(0, round(forecast_value, 4)),
                "lower_bound": max(0, round(forecast_value - margin, 4)),
                "upper_bound": round(forecast_value + margin, 4),
            })
        
        # Confidence based on data quality
        confidence = "high" if len(hourly_data) >= 168 and trend_info["r_squared"] > 0.7 else \
                     "medium" if len(hourly_data) >= 72 else "low"
        
        return {
            "forecast": forecast,
            "confidence": confidence,
            "trend": trend_info,
            "current_hourly_avg": round(np.mean(costs[-24:]), 4) if len(costs) >= 24 else round(np.mean(costs), 4),
            "predicted_next_4h_total": round(sum(f["predicted_cost"] for f in forecast), 4),
        }

    def detect_anomaly_risk(
        self,
        db: Session,
        project_id: str,
    ) -> dict[str, Any]:
        """Detect if cost anomaly is likely in the near future."""
        
        hourly_data = self.get_hourly_cost_data(db, project_id, hours_back=168)
        
        if len(hourly_data) < 24:
            return {
                "status": "insufficient_data",
                "risk_level": "unknown",
                "message": "Need at least 24 hours of data for forecasting",
            }
        
        forecast = self.forecast_cost(hourly_data, hours_ahead=self.forecast_horizon)
        
        # Get current spend rate
        recent_costs = [d["total_cost"] for d in hourly_data[-24:]]
        current_avg = np.mean(recent_costs)
        
        # Get baseline (7-day average, excluding last 24h)
        if len(hourly_data) >= 48:
            baseline_costs = [d["total_cost"] for d in hourly_data[-168:-24]]
            baseline_avg = np.mean(baseline_costs)
        else:
            baseline_avg = current_avg
        
        # Predicted vs baseline
        predicted_total = forecast["predicted_next_4h_total"]
        predicted_avg_hourly = predicted_total / self.forecast_horizon
        
        # Risk assessment
        risk_factors = []
        risk_score = 0
        
        # Factor 1: Trend direction
        if forecast["trend"]["trend"] == "increasing":
            risk_factors.append("cost_trend_increasing")
            risk_score += 20
        
        # Factor 2: Predicted exceeds baseline significantly
        if baseline_avg > 0:
            increase_ratio = predicted_avg_hourly / baseline_avg
            if increase_ratio > 2.0:
                risk_factors.append("predicted_double_baseline")
                risk_score += 40
            elif increase_ratio > 1.5:
                risk_factors.append("predicted_50pct_above_baseline")
                risk_score += 25
        
        # Factor 3: High variance in recent data
        recent_std = np.std(recent_costs)
        if current_avg > 0 and recent_std / current_avg > 0.5:
            risk_factors.append("high_cost_variance")
            risk_score += 15
        
        # Risk level
        if risk_score >= 60:
            risk_level = "high"
        elif risk_score >= 30:
            risk_level = "medium"
        elif risk_score > 0:
            risk_level = "low"
        else:
            risk_level = "normal"
        
        return {
            "status": "analyzed",
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_factors": risk_factors,
            "forecast": forecast,
            "baseline_avg_hourly": round(baseline_avg, 4),
            "current_avg_hourly": round(current_avg, 4),
            "predicted_avg_hourly": round(predicted_avg_hourly, 4),
            "recommendation": self._get_recommendation(risk_level, risk_factors),
        }
    
    def _get_recommendation(self, risk_level: str, factors: list[str]) -> str:
        """Get human-readable recommendation."""
        if risk_level == "high":
            return "Urgent: Cost spike likely. Review active agents and consider rate limiting."
        elif risk_level == "medium":
            return "Warning: Elevated cost risk detected. Monitor usage closely."
        elif "cost_trend_increasing" in factors:
            return "Advisory: Cost trend is increasing. Consider reviewing model selection."
        return "Normal: Cost patterns appear stable."


# Singleton instance
_cost_service: PredictiveCostService | None = None


def get_predictive_cost_service() -> PredictiveCostService:
    """Get or create predictive cost service singleton."""
    global _cost_service
    if _cost_service is None:
        _cost_service = PredictiveCostService()
    return _cost_service
