"""Runtime-enforced experiment lifecycle transitions."""

from datetime import datetime

from botnet_council.experiments.models import (
    ExperimentRecord,
    ExperimentState,
    LifecycleEvent,
)

_ALLOWED: dict[ExperimentState, frozenset[ExperimentState]] = {
    ExperimentState.CREATED: frozenset({ExperimentState.CONTEXT_READY, ExperimentState.FAILED}),
    ExperimentState.CONTEXT_READY: frozenset({ExperimentState.FORECASTING, ExperimentState.FAILED}),
    ExperimentState.FORECASTING: frozenset(
        {ExperimentState.FORECAST_LOCKED, ExperimentState.FAILED}
    ),
    ExperimentState.FORECAST_LOCKED: frozenset(
        {ExperimentState.EVALUATING, ExperimentState.FAILED}
    ),
    ExperimentState.EVALUATING: frozenset({ExperimentState.COMPLETE, ExperimentState.FAILED}),
    ExperimentState.COMPLETE: frozenset(),
    ExperimentState.FAILED: frozenset(),
}


def transition(
    record: ExperimentRecord,
    state: ExperimentState,
    occurred_at: datetime,
    *,
    message: str = "",
    **updates: object,
) -> ExperimentRecord:
    if state not in _ALLOWED[record.state]:
        raise ValueError(f"invalid experiment transition {record.state.value} -> {state.value}")
    values = record.model_dump(mode="python", warnings=False)
    values.update(
        {
            "state": state,
            "lifecycle": record.lifecycle
            + (LifecycleEvent(state=state, occurred_at=occurred_at, message=message),),
            **updates,
        }
    )
    return ExperimentRecord.model_validate(values)
