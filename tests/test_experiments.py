from datetime import UTC, datetime, timedelta
from inspect import signature
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from botnet_council.api import create_app
from botnet_council.council import CouncilConfig
from botnet_council.experiments import (
    ExperimentContext,
    ExperimentRequest,
    ExperimentService,
    ExperimentState,
    FileExperimentRepository,
    HistoricalExperimentSelector,
    InMemoryExperimentRepository,
    RandomExperimentRequest,
    transition,
)
from botnet_council.experiments.forecasting import BlindForecaster
from botnet_council.experiments.models import ExperimentAgentConfig
from botnet_council.market_data import (
    Asset,
    InMemoryHistoricalProvider,
    Instrument,
    ProviderId,
    Timeframe,
)
from botnet_council.market_data.models import HistoricalRequest
from botnet_council.schemas import MarketBar

BASE = datetime(2024, 1, 1, tzinfo=UTC)
INSTRUMENT = Instrument(base=Asset.BTC, quote=Asset.USD)
CONTROL_TOKEN = "synthetic-control-token-32-characters"
CONTROL_HEADERS = {"authorization": f"Bearer {CONTROL_TOKEN}"}


def _bars(
    prices: tuple[float, ...], *, delayed: frozenset[int] = frozenset()
) -> tuple[MarketBar, ...]:
    return tuple(
        MarketBar(
            opened_at=BASE + index * timedelta(hours=1),
            closed_at=BASE + (index + 1) * timedelta(hours=1),
            available_at=BASE + (index + 1 + (10 if index in delayed else 0)) * timedelta(hours=1),
            open=price,
            high=price + 1.0,
            low=max(0.01, price - 1.0),
            close=price,
            volume=1.0,
        )
        for index, price in enumerate(prices)
    )


def _provider(prices: tuple[float, ...]) -> InMemoryHistoricalProvider:
    return InMemoryHistoricalProvider(
        instrument=INSTRUMENT,
        timeframe=Timeframe.HOUR_1,
        bars=_bars(prices),
        fetched_at=BASE + timedelta(days=2),
    )


def _request(*, evaluation_hour: int = 4, seed: int | None = 7) -> ExperimentRequest:
    return ExperimentRequest(
        instrument="BTC/USD",
        provider=ProviderId.IN_MEMORY,
        evaluation_time=BASE + timedelta(hours=evaluation_hour),
        forecast_horizon="2h",
        timeframe="1h",
        agents=(
            ExperimentAgentConfig(kind="trend", parameters={"fast_window": 2, "slow_window": 3}),
        ),
        council=CouncilConfig(minimum_confidence=0.0, minimum_conviction=0.0),
        random_seed=seed,
    )


def _run(prices: tuple[float, ...]) -> tuple[ExperimentService, object]:
    service = ExperimentService(_provider(prices), InMemoryExperimentRepository())
    record = service.create(_request())
    return service, service.run(record.experiment_id)


def test_positive_forecast_positive_outcome_is_hand_verifiable() -> None:
    _, value = _run((90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0, 125.0))
    record = value
    assert record.state is ExperimentState.COMPLETE
    assert tuple(item.state for item in record.lifecycle) == (
        ExperimentState.CREATED,
        ExperimentState.CONTEXT_READY,
        ExperimentState.FORECASTING,
        ExperimentState.FORECAST_LOCKED,
        ExperimentState.EVALUATING,
        ExperimentState.COMPLETE,
    )
    assert record.forecast is not None and record.forecast.expected_return > 0
    assert record.oracle_outcome is not None
    assert record.oracle_outcome.start_price == 105.0
    assert record.oracle_outcome.endpoint_price == 115.0
    assert record.oracle_outcome.realized_return == pytest.approx(115 / 105 - 1)
    assert record.evaluation is not None
    assert record.evaluation.directional_correctness is True
    assert record.evaluation.absolute_return_error == pytest.approx(
        abs(record.forecast.expected_return - (115 / 105 - 1))
    )


def test_positive_forecast_negative_outcome_and_correct_direction_wrong_magnitude() -> None:
    _, wrong = _run((90.0, 95.0, 100.0, 105.0, 80.0, 70.0, 65.0))
    assert wrong.evaluation is not None
    assert wrong.evaluation.directional_correctness is False
    assert wrong.evaluation.realized_return < 0

    _, magnitude = _run((90.0, 95.0, 100.0, 105.0, 106.0, 107.0, 108.0))
    assert magnitude.evaluation is not None
    assert magnitude.evaluation.directional_correctness is True
    assert magnitude.evaluation.absolute_return_error > 0


def test_flat_outcome_uses_explicit_flat_direction() -> None:
    _, record = _run((90.0, 95.0, 100.0, 105.0, 106.0, 105.0, 105.0))
    assert record.oracle_outcome is not None
    assert record.oracle_outcome.realized_return == 0.0
    assert record.oracle_outcome.realized_direction.value == "flat"
    assert record.evaluation is not None
    assert record.evaluation.directional_correctness is False


def test_unavailable_horizon_fails_after_preserving_locked_forecast() -> None:
    service, record = _run((90.0, 95.0, 100.0, 105.0, 110.0))
    assert record.state is ExperimentState.FAILED
    assert record.forecast is not None
    assert record.oracle_outcome is not None
    assert record.oracle_outcome.horizon_complete is False
    assert record.evaluation is None
    assert service.forecast(record.experiment_id) == record.forecast


def test_insufficient_context_fails_before_forecasting() -> None:
    provider = _provider((100.0, 101.0))
    service = ExperimentService(provider, InMemoryExperimentRepository())
    record = service.run(service.create(_request()).experiment_id)
    assert record.state is ExperimentState.FAILED
    assert record.error == "insufficient complete historical context"
    assert record.forecast is None


def test_future_prices_do_not_change_forecast_and_context_has_no_oracle_shape() -> None:
    prefix = (90.0, 95.0, 100.0, 105.0)
    up_service, up = _run(prefix + (110.0, 120.0, 130.0))
    _, down = _run(prefix + (80.0, 70.0, 60.0))
    assert up.forecast == down.forecast
    assert up.oracle_outcome != down.oracle_outcome
    stored_context = up_service.get(up.experiment_id).context
    assert stored_context is not None
    assert "oracle_outcome" not in ExperimentContext.model_fields
    assert all(
        bar.available_at <= stored_context.evaluation_time for bar in stored_context.snapshot.bars
    )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExperimentContext.model_validate(
            {
                **stored_context.model_dump(warnings=False),
                "oracle_outcome": {"realized_return": 1.0},
            }
        )
    assert "oracle" not in signature(BlindForecaster.forecast).parameters


def test_forecast_is_immutable_and_evaluation_does_not_mutate_it() -> None:
    repository = InMemoryExperimentRepository()
    service = ExperimentService(_provider((90.0, 95.0, 100.0, 105.0, 110.0, 115.0)), repository)
    record = service.run(service.create(_request()).experiment_id)
    assert record.forecast is not None
    original = record.forecast
    changed = record.model_copy(
        update={"forecast": original.model_copy(update={"confidence": 0.0})}
    )
    with pytest.raises(ValueError, match="immutable"):
        repository.save(changed)
    assert repository.get(record.experiment_id).forecast == original


def test_oracle_provider_call_occurs_only_after_persisted_forecast_lock() -> None:
    repository = InMemoryExperimentRepository()
    delegate = _provider((90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0))

    class BarrierProvider:
        metadata = delegate.metadata
        source_version = delegate.source_version
        adapter_semantic_version = delegate.adapter_semantic_version

        def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> object:
            return delegate.snapshot(symbol, timeframe, as_of=as_of)

        def fetch_historical(self, request: HistoricalRequest) -> object:
            if request.as_of > _request().evaluation_time:
                persisted = repository.get(_request().experiment_id)
                assert persisted.state is ExperimentState.EVALUATING
                assert persisted.forecast is not None
            return delegate.fetch_historical(request)

    service = ExperimentService(BarrierProvider(), repository)  # type: ignore[arg-type]
    record = service.run(service.create(_request()).experiment_id)
    assert record.state is ExperimentState.COMPLETE


def test_file_repository_round_trip_preserves_separate_provenance(tmp_path: Path) -> None:
    repository = FileExperimentRepository(tmp_path / "experiments")
    service = ExperimentService(
        _provider((90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0)), repository
    )
    record = service.run(service.create(_request()).experiment_id)
    loaded = repository.get(record.experiment_id)
    assert loaded == record
    assert loaded.forecast is not None and loaded.oracle_outcome is not None
    assert (
        loaded.forecast.source_provenance.content_identity
        != loaded.oracle_outcome.provenance.content_identity
    )


def test_invalid_lifecycle_transition_is_rejected() -> None:
    service = ExperimentService(
        _provider((90.0, 95.0, 100.0, 105.0)), InMemoryExperimentRepository()
    )
    record = service.create(_request())
    with pytest.raises(ValueError, match="invalid experiment transition"):
        transition(record, ExperimentState.EVALUATING, record.request.evaluation_time)


def test_seeded_selection_is_deterministic_and_excludes_incomplete_points() -> None:
    provider = _provider(tuple(100.0 + index for index in range(16)))
    selector = HistoricalExperimentSelector(provider)
    selection = RandomExperimentRequest(
        template=_request(seed=None),
        range_start=BASE + timedelta(hours=4),
        range_end=BASE + timedelta(hours=10),
        samples=3,
        seed=42,
    )
    first = selector.select(selection)
    second = selector.select(selection)
    assert first == second
    assert len({item.evaluation_time for item in first}) == 3
    assert all(item.random_seed == 42 for item in first)


def test_repeated_experiment_is_reproducible_and_create_is_idempotent() -> None:
    provider = _provider((90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0))
    first_service = ExperimentService(provider, InMemoryExperimentRepository())
    second_service = ExperimentService(provider, InMemoryExperimentRepository())
    first_created = first_service.create(_request())
    assert first_service.create(_request()) == first_created
    first = first_service.run(first_created.experiment_id)
    second = second_service.run(second_service.create(_request()).experiment_id)
    assert first.forecast == second.forecast
    assert first.oracle_outcome == second.oracle_outcome
    assert first.evaluation == second.evaluation


def test_human_api_exposes_oracle_only_after_lock_and_never_exposes_context() -> None:
    service = ExperimentService(
        _provider((90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0)),
        InMemoryExperimentRepository(),
    )
    client = TestClient(
        create_app(experiment_service=service, command_token=CONTROL_TOKEN)
    )
    body = {
        "instrument": "BTC/USD",
        "provider": "in_memory",
        "evaluation_time": "2024-01-01T04:00:00Z",
        "forecast_horizon": "2h",
        "timeframe": "1h",
        "agents": [{"kind": "trend", "parameters": {"fast_window": 2, "slow_window": 3}}],
        "council": {"minimum_confidence": 0.0, "minimum_conviction": 0.0},
        "random_seed": 7,
    }
    created = client.post("/api/control/experiments", json=body, headers=CONTROL_HEADERS)
    assert created.status_code == 201, created.text
    experiment_id = created.json()["experiment"]["experiment_id"]
    assert client.get(f"/api/experiments/{experiment_id}/oracle").status_code == 409
    completed = client.post(
        f"/api/control/experiments/{experiment_id}/run", headers=CONTROL_HEADERS
    )
    assert completed.status_code == 200
    assert "context" not in completed.json()["experiment"]
    oracle = client.get(f"/api/experiments/{experiment_id}/oracle")
    assert oracle.status_code == 200
    assert oracle.json()["oracle_outcome"]["realized_return"] == pytest.approx(115 / 105 - 1)
    assert client.get(f"/api/experiments/{experiment_id}/evaluation").status_code == 200

    invalid = client.post(
        "/api/control/experiments",
        json={**body, "forecast_horizon": "not-a-duration"},
        headers=CONTROL_HEADERS,
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_command_access_policy_rejects_untrusted_and_unauthenticated_requests() -> None:
    service = ExperimentService(
        _provider((90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0)),
        InMemoryExperimentRepository(),
    )
    created = service.create(_request())
    client = TestClient(
        create_app(experiment_service=service, command_token=CONTROL_TOKEN)
    )
    target = f"/api/control/experiments/{created.experiment_id}/run"

    unauthenticated = client.post(target)
    unauthenticated_untrusted_origin = client.post(
        target, headers={"origin": "https://evil.example"}
    )
    untrusted_origin = client.post(
        target,
        headers={**CONTROL_HEADERS, "origin": "https://evil.example"},
    )

    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"
    assert unauthenticated_untrusted_origin.status_code == 403
    assert untrusted_origin.status_code == 403
    assert service.get(created.experiment_id).state is ExperimentState.CREATED

    health = client.get("/api/health").json()
    assert health["read_only"] is False
    assert health["command_authentication"] == "bearer_token"
    assert "experiment_control" in health["capabilities"]

    openapi = client.get("/openapi.json").json()
    for path in (
        "/api/control/experiments",
        "/api/control/experiments/{experiment_id}/run",
        "/api/control/experiment-batches/run",
    ):
        assert openapi["paths"][path]["post"]["security"] == [{"HTTPBearer": []}]

    completed = client.post(
        target,
        headers={**CONTROL_HEADERS, "origin": "http://localhost:5173"},
    )
    assert completed.status_code == 200
    assert service.get(created.experiment_id).state is ExperimentState.COMPLETE


def test_command_routes_are_disabled_without_a_configured_token() -> None:
    service = ExperimentService(
        _provider((90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0)),
        InMemoryExperimentRepository(),
    )
    created = service.create(_request())
    client = TestClient(create_app(experiment_service=service))

    response = client.post(
        f"/api/control/experiments/{created.experiment_id}/run",
        headers=CONTROL_HEADERS,
    )

    assert response.status_code == 503
    assert service.get(created.experiment_id).state is ExperimentState.CREATED


def test_random_batch_preserves_individuals_and_reports_aggregates() -> None:
    provider = _provider(tuple(100.0 + index for index in range(20)))
    service = ExperimentService(provider, InMemoryExperimentRepository())
    result = service.run_random_batch(
        RandomExperimentRequest(
            template=_request(seed=None),
            range_start=BASE + timedelta(hours=4),
            range_end=BASE + timedelta(hours=10),
            samples=3,
            seed=11,
        )
    )
    assert result.selection_seed == 11
    assert result.experiment_count == 3
    assert result.directional_accuracy == 1.0
    assert len(result.confidence_calibration) >= 1
    assert len(result.performance_by_configuration) == 1
    assert all(
        service.get(item).state is ExperimentState.COMPLETE for item in result.experiment_ids
    )
