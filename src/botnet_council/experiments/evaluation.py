"""Transparent forecast-versus-outcome measurements."""

from botnet_council.experiments.models import Forecast, ForecastEvaluation, OracleOutcome


def evaluate(forecast: Forecast, outcome: OracleOutcome) -> ForecastEvaluation:
    if forecast.experiment_id != outcome.experiment_id:
        raise ValueError("forecast and oracle outcome belong to different experiments")
    if not outcome.horizon_complete:
        raise ValueError("cannot evaluate an incomplete oracle horizon")
    if outcome.realized_return is None or outcome.realized_direction is None:
        raise ValueError("complete oracle outcome is missing measurements")
    expected = forecast.expected_return
    signed_error = None if expected is None else expected - outcome.realized_return
    bucket_start = min(int(forecast.confidence * 10), 9) * 10
    return ForecastEvaluation(
        experiment_id=forecast.experiment_id,
        forecast_id=forecast.forecast_id,
        directional_correctness=forecast.direction is outcome.realized_direction,
        forecast_direction=forecast.direction,
        realized_direction=outcome.realized_direction,
        expected_return=expected,
        realized_return=outcome.realized_return,
        absolute_return_error=None if signed_error is None else abs(signed_error),
        signed_return_error=signed_error,
        confidence=forecast.confidence,
        calibration_bucket=f"{bucket_start:02d}-{bucket_start + 10:02d}%",
        evaluated_at=outcome.horizon_end,
    )
