"""FastAPI application backed exclusively by public telemetry events."""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from collections.abc import Mapping
from hmac import compare_digest
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from botnet_council import __version__
from botnet_council.council import CouncilConfig
from botnet_council.experience import EpisodeQuery, ExperienceStore
from botnet_council.experiments import (
    ExperimentRequest,
    ExperimentService,
    FileExperimentRepository,
    RandomExperimentRequest,
)
from botnet_council.experiments.models import ExperimentAgentConfig
from botnet_council.learning import WeightProfileStore
from botnet_council.market_data import (
    CachedHistoricalProvider,
    KrakenHistoricalProvider,
    ParquetMarketDataCache,
    ProviderId,
)
from botnet_council.telemetry.contracts import (
    API_VERSION,
    AgentDetailResponse,
    AgentPage,
    BootstrapResponse,
    DecisionDetailResponse,
    ErrorResponse,
    EventPage,
    EventType,
    ExperiencePage,
    ExperienceResponse,
    ExperimentBatchResponse,
    ExperimentCreateRequest,
    ExperimentEvaluationResponse,
    ExperimentForecastResponse,
    ExperimentOracleResponse,
    ExperimentPage,
    ExperimentResponse,
    HealthResponse,
    LearningReviewPage,
    PortfolioResponse,
    RandomExperimentCreateRequest,
    RunDetailResponse,
    RunKind,
    RunPage,
    SnapshotResponse,
    StateResponse,
    TelemetryEvent,
    WeightGenerationPage,
)
from botnet_council.telemetry.publisher import EventBusSnapshot, EventFilter, InMemoryEventBus
from botnet_council.telemetry.serializers import (
    experience_detail,
    experience_summary,
    experiment_batch,
    experiment_evaluation,
    experiment_forecast,
    experiment_oracle,
    experiment_summary,
    learning_review,
    weight_generation,
)

DEFAULT_WEBSOCKET_QUEUE_LIMIT = 256
MINIMUM_CONTROL_TOKEN_LENGTH = 32
CONTROL_TOKEN_ENVIRONMENT_VARIABLE = "BOTNET_COUNCIL_CONTROL_TOKEN"
EXPERIENCE_STORE_ENVIRONMENT_VARIABLE = "BOTNET_COUNCIL_EXPERIENCE_STORE"
WEIGHT_STORE_ENVIRONMENT_VARIABLE = "BOTNET_COUNCIL_WEIGHT_STORE"
CONTROL_BEARER = HTTPBearer(auto_error=False)
ALLOWED_BROWSER_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }
)


def create_app(
    bus: InMemoryEventBus | None = None,
    *,
    websocket_queue_limit: int = DEFAULT_WEBSOCKET_QUEUE_LIMIT,
    experiment_service: ExperimentService | None = None,
    experience_store: ExperienceStore | None = None,
    weight_store: WeightProfileStore | None = None,
    command_token: str | None = None,
) -> FastAPI:
    if websocket_queue_limit < 1:
        raise ValueError("websocket_queue_limit must be positive")
    telemetry = bus or InMemoryEventBus()
    experiments = experiment_service or _default_experiment_service()
    experiences = experience_store or _configured_experience_store()
    weights = weight_store or _configured_weight_store()
    control_token = command_token or os.environ.get(CONTROL_TOKEN_ENVIRONMENT_VARIABLE)
    if control_token is not None and len(control_token) < MINIMUM_CONTROL_TOKEN_LENGTH:
        raise ValueError("command_token must contain at least 32 characters")
    app = FastAPI(
        title="Botnet Council Telemetry API",
        version=API_VERSION,
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.telemetry = telemetry
    app.state.experiments = experiments
    app.state.experiences = experiences
    app.state.weights = weights

    async def require_command_access(
        request: Request,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(CONTROL_BEARER)
        ],
    ) -> None:
        if control_token is None:
            raise HTTPException(503, "experiment control is disabled")
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_BROWSER_ORIGINS:
            raise HTTPException(403, "origin is not allowed")
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or not compare_digest(credentials.credentials, control_token)
        ):
            raise HTTPException(
                401,
                "command authorization failed",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.middleware("http")
    async def request_id(request: Request, call_next: Any) -> Any:
        identifier = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = identifier
        response = await call_next(request)
        response.headers["x-request-id"] = identifier
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail
        message = str(detail) if isinstance(detail, str) else "request failed"
        return _error(
            request,
            error.status_code,
            "http_error",
            message,
            detail,
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        details = [
            {key: value for key, value in item.items() if key in {"type", "loc", "msg"}}
            for item in error.errors()
        ]
        return _error(request, 422, "validation_error", "request validation failed", details)

    @app.exception_handler(ValidationError)
    async def domain_validation_error(request: Request, error: ValidationError) -> JSONResponse:
        details = [
            {key: value for key, value in item.items() if key in {"type", "loc", "msg"}}
            for item in error.errors()
        ]
        return _error(request, 422, "validation_error", "request validation failed", details)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception) -> JSONResponse:
        del error
        return _error(request, 500, "internal_error", "internal server error")

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> dict[str, Any]:
        control_enabled = control_token is not None
        return {
            "api_version": API_VERSION,
            "status": "ok",
            "service": "botnet-council-telemetry",
            "backend_version": __version__,
            "read_only": not control_enabled,
            "capabilities": (
                "telemetry_read",
                "experiment_read",
                *(("experience_read",) if experiences is not None else ()),
                *(("learning_read",) if weights is not None else ()),
                *(("experiment_control",) if control_enabled else ()),
            ),
            "command_authentication": "bearer_token" if control_enabled else "disabled",
        }

    @app.get("/api/state", response_model=StateResponse)
    async def state() -> dict[str, Any]:
        return _state(telemetry.snapshot())

    @app.get("/api/bootstrap", response_model=BootstrapResponse)
    async def bootstrap() -> dict[str, Any]:
        snapshot = telemetry.snapshot()
        runs = _run_values(snapshot.events)
        agents = _agent_values(snapshot.events)
        return {
            "api_version": API_VERSION,
            "stream_id": snapshot.stream_id,
            "sequence_watermark": snapshot.sequence_watermark,
            "state": _state(snapshot),
            "runs": runs,
            "agents": agents,
            "events": snapshot.events,
        }

    @app.get(
        "/api/portfolio",
        response_model=PortfolioResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_portfolio() -> dict[str, Any]:
        item = _last(telemetry, EventType.PORTFOLIO_UPDATED)
        if item is None:
            raise HTTPException(404, "portfolio state is not available")
        return {"api_version": API_VERSION, "portfolio": _payload(item)}

    @app.get("/api/decisions", response_model=EventPage)
    async def decisions(
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        items = _of_type(telemetry, EventType.COUNCIL_DECISION_EMITTED)
        return _page(items, limit, offset)

    @app.get(
        "/api/decisions/{decision_id}",
        response_model=DecisionDetailResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def decision(decision_id: str) -> dict[str, Any]:
        events = tuple(
            item
            for item in telemetry.list_events()
            if item.correlation_id == decision_id
            or (
                isinstance(item.payload, dict)
                and item.payload.get("decision_id") == decision_id
            )
        )
        # Public payloads are models, so correlation_id is the canonical join.
        if not events:
            events = tuple(
                item
                for item in telemetry.list_events()
                if getattr(item.payload, "decision_id", None) == decision_id
            )
        if not events:
            raise HTTPException(404, "decision was not found")
        run_id = events[0].run_id
        snapshot_id = events[0].source_snapshot_id
        signals = tuple(
            item
            for item in telemetry.list_events(EventFilter(run_id=run_id))
            if item.event_type is EventType.AGENT_SIGNAL_EMITTED
            and item.source_snapshot_id == snapshot_id
        )
        unique = {item.event_id: item for item in (*events, *signals)}
        chain = tuple(sorted(unique.values(), key=lambda item: item.sequence))
        return {
            "api_version": API_VERSION,
            "decision_id": decision_id,
            "events": chain,
        }

    @app.get("/api/runs", response_model=RunPage)
    async def runs(
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        values = _run_values(telemetry.list_events())
        return _page_values(values, limit, offset)

    @app.get(
        "/api/runs/{run_id}",
        response_model=RunDetailResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def run(run_id: str) -> dict[str, Any]:
        items = telemetry.list_events(EventFilter(run_id=run_id))
        if not items:
            raise HTTPException(404, "run was not found")
        return {
            "api_version": API_VERSION,
            "run_id": run_id,
            "events": items,
        }

    @app.get(
        "/api/snapshots/{snapshot_id}",
        response_model=SnapshotResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def snapshot(snapshot_id: str) -> dict[str, Any]:
        item = next(
            (
                event
                for event in telemetry.list_events()
                if event.event_type is EventType.SNAPSHOT_CREATED
                and event.source_snapshot_id == snapshot_id
            ),
            None,
        )
        if item is None:
            raise HTTPException(404, "snapshot was not found")
        return {"api_version": API_VERSION, "snapshot": _payload(item)}

    @app.get("/api/backtests", response_model=RunPage)
    async def backtests(
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        values = tuple(
            item for item in _run_values(telemetry.list_events())
            if item["run_kind"] is RunKind.BACKTEST
        )
        return _page_values(values, limit, offset)

    @app.get(
        "/api/backtests/{run_id}",
        response_model=RunDetailResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def backtest(run_id: str) -> dict[str, Any]:
        items = tuple(
            item
            for item in telemetry.list_events(EventFilter(run_id=run_id))
            if item.event_type.value.startswith("backtest_")
        )
        if not items:
            raise HTTPException(404, "backtest was not found")
        return {
            "api_version": API_VERSION,
            "run_id": run_id,
            "events": items,
        }

    @app.get("/api/agents", response_model=AgentPage)
    async def agents(
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        latest: dict[str, TelemetryEvent] = {}
        for item in _of_type(telemetry, EventType.AGENT_SIGNAL_EMITTED):
            agent_id = getattr(item.payload, "agent_id", None)
            if isinstance(agent_id, str):
                latest[agent_id] = item
        values = tuple(
            {
                "agent_id": key,
                "agent_version": value.payload.agent_version,  # type: ignore[union-attr]
                "latest_signal": value,
            }
            for key, value in sorted(latest.items())
        )
        return _page_values(values, limit, offset)

    @app.get(
        "/api/agents/{agent_id}",
        response_model=AgentDetailResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def agent(agent_id: str) -> dict[str, Any]:
        items = tuple(
            item
            for item in _of_type(telemetry, EventType.AGENT_SIGNAL_EMITTED)
            if getattr(item.payload, "agent_id", None) == agent_id
        )
        if not items:
            raise HTTPException(404, "agent was not found")
        return {
            "api_version": API_VERSION,
            "agent_id": agent_id,
            "signals": items,
        }

    @app.get(
        "/api/experiences",
        response_model=ExperiencePage,
        responses={503: {"model": ErrorResponse}},
    )
    async def experience_episodes(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        symbol: str | None = None,
        training_only: bool = False,
    ) -> dict[str, Any]:
        if experiences is None:
            raise HTTPException(503, "experience store is not configured")
        values = experiences.query(
            EpisodeQuery(symbol=symbol, training_only=training_only)
        )
        summaries = tuple(experience_summary(item) for item in values)
        return {
            "api_version": API_VERSION,
            "items": summaries[offset : offset + limit],
            "total": len(summaries),
            "limit": limit,
            "offset": offset,
        }

    @app.get(
        "/api/experiences/{episode_id}",
        response_model=ExperienceResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def experience_episode(episode_id: str) -> dict[str, Any]:
        if experiences is None:
            raise HTTPException(503, "experience store is not configured")
        try:
            value = experiences.get(episode_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        return {"api_version": API_VERSION, "episode": experience_detail(value)}

    @app.get(
        "/api/weight-generations",
        response_model=WeightGenerationPage,
        responses={503: {"model": ErrorResponse}},
    )
    async def weight_generations() -> dict[str, Any]:
        if weights is None:
            raise HTTPException(503, "weight profile store is not configured")
        values = weights.list()
        try:
            active_generation_id = weights.active().generation_id
        except LookupError:
            active_generation_id = None
        return {
            "api_version": API_VERSION,
            "active_generation_id": active_generation_id,
            "items": tuple(weight_generation(item) for item in values),
            "total": len(values),
        }

    @app.get(
        "/api/learning-reviews",
        response_model=LearningReviewPage,
        responses={503: {"model": ErrorResponse}},
    )
    async def learning_reviews() -> dict[str, Any]:
        if weights is None:
            raise HTTPException(503, "weight profile store is not configured")
        values = weights.list_reviews()
        return {
            "api_version": API_VERSION,
            "items": tuple(learning_review(item) for item in values),
            "total": len(values),
        }

    @app.post(
        "/api/control/experiments",
        response_model=ExperimentResponse,
        status_code=201,
        responses={422: {"model": ErrorResponse}},
        dependencies=[Depends(require_command_access)],
    )
    async def create_experiment(body: ExperimentCreateRequest) -> dict[str, Any]:
        try:
            record = experiments.create(_experiment_request(body))
        except ValidationError:
            raise
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {"api_version": API_VERSION, "experiment": experiment_summary(record)}

    @app.post(
        "/api/control/experiments/{experiment_id}/run",
        response_model=ExperimentResponse,
        responses={404: {"model": ErrorResponse}},
        dependencies=[Depends(require_command_access)],
    )
    async def run_experiment(experiment_id: str) -> dict[str, Any]:
        try:
            record = experiments.run(experiment_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"api_version": API_VERSION, "experiment": experiment_summary(record)}

    @app.post(
        "/api/control/experiment-batches/run",
        response_model=ExperimentBatchResponse,
        dependencies=[Depends(require_command_access)],
    )
    async def run_experiment_batch(body: RandomExperimentCreateRequest) -> Any:
        try:
            request = RandomExperimentRequest(
                template=_experiment_request(body.template),
                range_start=body.range_start,
                range_end=body.range_end,
                samples=body.samples,
                seed=body.seed,
            )
            return experiment_batch(experiments.run_random_batch(request))
        except ValidationError:
            raise
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/api/experiments", response_model=ExperimentPage)
    async def list_experiments(
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        values = tuple(experiment_summary(item) for item in experiments.list())
        return {
            "api_version": API_VERSION,
            "items": values[offset : offset + limit],
            "total": len(values),
            "limit": limit,
            "offset": offset,
        }

    @app.get(
        "/api/experiments/{experiment_id}",
        response_model=ExperimentResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def experiment_status(experiment_id: str) -> dict[str, Any]:
        try:
            record = experiments.get(experiment_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        return {"api_version": API_VERSION, "experiment": experiment_summary(record)}

    @app.get(
        "/api/experiments/{experiment_id}/forecast",
        response_model=ExperimentForecastResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def experiment_forecast_result(experiment_id: str) -> dict[str, Any]:
        try:
            value = experiments.forecast(experiment_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        return {"api_version": API_VERSION, "forecast": experiment_forecast(value)}

    @app.get(
        "/api/experiments/{experiment_id}/oracle",
        response_model=ExperimentOracleResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def experiment_oracle_result(experiment_id: str) -> dict[str, Any]:
        try:
            value = experiments.oracle_outcome(experiment_id)
        except PermissionError as error:
            raise HTTPException(409, str(error)) from error
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        return {"api_version": API_VERSION, "oracle_outcome": experiment_oracle(value)}

    @app.get(
        "/api/experiments/{experiment_id}/evaluation",
        response_model=ExperimentEvaluationResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def experiment_evaluation_result(experiment_id: str) -> dict[str, Any]:
        try:
            value = experiments.evaluation(experiment_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        return {"api_version": API_VERSION, "evaluation": experiment_evaluation(value)}

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in ALLOWED_BROWSER_ORIGINS:
            await websocket.close(code=1008, reason="origin is not allowed")
            return
        try:
            event_types = _parse_event_types(websocket.query_params.get("event_type"))
        except ValueError as error:
            await websocket.accept()
            await websocket.send_json(
                {"type": "stream_error", "code": "invalid_filter", "message": str(error)}
            )
            await websocket.close(code=1008)
            return
        await websocket.accept()
        event_filter = EventFilter(
            symbol=websocket.query_params.get("symbol"),
            run_id=websocket.query_params.get("run_id"),
            timeframe=websocket.query_params.get("timeframe"),
            event_types=event_types,
        )
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[TelemetryEvent | None] = asyncio.Queue(
            maxsize=websocket_queue_limit
        )

        def enqueue(item: TelemetryEvent) -> None:
            def put() -> None:
                _enqueue_or_lag(queue, item)

            loop.call_soon_threadsafe(put)

        subscription_id = telemetry.subscribe(enqueue, event_filter)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    await websocket.send_json(
                        {
                            "type": "stream_error",
                            "code": "consumer_lagged",
                            "message": "consumer fell behind; REST resynchronization required",
                            "stream_id": telemetry.stream_id,
                        }
                    )
                    await websocket.close(code=1013)
                    return
                await websocket.send_json(_event_json(item))
        except WebSocketDisconnect:
            pass
        finally:
            telemetry.unsubscribe(subscription_id)

    return app


def _default_experiment_service() -> ExperimentService:
    provider = CachedHistoricalProvider(
        KrakenHistoricalProvider(), ParquetMarketDataCache(Path(".market-data-cache"))
    )
    return ExperimentService(provider, FileExperimentRepository(Path("experiment-results")))


def _configured_experience_store() -> ExperienceStore | None:
    root = os.environ.get(EXPERIENCE_STORE_ENVIRONMENT_VARIABLE)
    return None if root is None else ExperienceStore(Path(root))


def _configured_weight_store() -> WeightProfileStore | None:
    root = os.environ.get(WEIGHT_STORE_ENVIRONMENT_VARIABLE)
    return None if root is None else WeightProfileStore(Path(root))


def _experiment_request(body: ExperimentCreateRequest) -> ExperimentRequest:
    return ExperimentRequest(
        instrument=body.instrument,
        provider=ProviderId(body.provider),
        evaluation_time=body.evaluation_time,
        forecast_horizon=body.forecast_horizon,
        timeframe=body.timeframe,
        agents=tuple(
            ExperimentAgentConfig(kind=item.kind, parameters=item.parameters)
            for item in body.agents
        ),
        council=CouncilConfig(
            agent_weights=body.council.agent_weights,
            minimum_confidence=body.council.minimum_confidence,
            minimum_conviction=body.council.minimum_conviction,
        ),
        random_seed=body.random_seed,
        context_bars=body.context_bars,
    )


def _error(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: Any = None,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "api_version": API_VERSION,
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": getattr(request.state, "request_id", str(uuid4())),
            },
        },
        headers=headers,
    )


def _event_json(item: TelemetryEvent) -> dict[str, Any]:
    return item.model_dump(mode="json")


def _payload(item: TelemetryEvent | None) -> Any:
    return None if item is None else item.payload


def _of_type(bus: InMemoryEventBus, event_type: EventType) -> tuple[TelemetryEvent, ...]:
    return bus.list_events(EventFilter(event_types=frozenset({event_type})))


def _last(bus: InMemoryEventBus, event_type: EventType) -> TelemetryEvent | None:
    items = _of_type(bus, event_type)
    return items[-1] if items else None


def _latest_by_type(events: tuple[TelemetryEvent, ...]) -> dict[EventType, TelemetryEvent]:
    return {item.event_type: item for item in events}


def _state(snapshot: EventBusSnapshot) -> dict[str, Any]:
    events = snapshot.events
    latest = _latest_by_type(events)
    return {
        "api_version": API_VERSION,
        "stream_id": snapshot.stream_id,
        "sequence_watermark": snapshot.sequence_watermark,
        "event_count": len(events),
        "last_sequence": snapshot.sequence_watermark,
        "latest_portfolio": _payload(latest.get(EventType.PORTFOLIO_UPDATED)),
        "latest_decision": _payload(latest.get(EventType.COUNCIL_DECISION_EMITTED)),
        "latest_risk_decision": _payload(latest.get(EventType.RISK_DECISION_EMITTED)),
        "active_runs": _active_run_ids(events),
    }


def _active_run_ids(events: tuple[TelemetryEvent, ...]) -> tuple[str, ...]:
    active: set[str] = set()
    for item in events:
        if item.event_type in {EventType.PIPELINE_STARTED, EventType.BACKTEST_STARTED}:
            active.add(item.run_id)
        elif item.event_type in {
            EventType.PIPELINE_COMPLETED,
            EventType.PIPELINE_FAILED,
            EventType.BACKTEST_COMPLETED,
        }:
            active.discard(item.run_id)
    return tuple(sorted(active))


def _group_runs(events: tuple[TelemetryEvent, ...]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[TelemetryEvent]] = defaultdict(list)
    for item in events:
        grouped[item.run_id].append(item)
    return {
        run_id: {
            "run_id": run_id,
            "run_kind": _run_kind(items),
            "first_sequence": items[0].sequence,
            "last_sequence": items[-1].sequence,
            "started_at": items[0].emitted_at,
            "updated_at": items[-1].emitted_at,
            "event_count": len(items),
            "status": _run_status(items),
            "symbol": next((item.symbol for item in items if item.symbol), None),
            "timeframe": next((item.timeframe for item in items if item.timeframe), None),
        }
        for run_id, items in grouped.items()
    }


def _run_kind(items: list[TelemetryEvent]) -> RunKind:
    return (
        RunKind.BACKTEST
        if any(item.event_type.value.startswith("backtest_") for item in items)
        else RunKind.PIPELINE
    )


def _run_values(events: tuple[TelemetryEvent, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        sorted(
            _group_runs(events).values(),
            key=lambda item: (item["updated_at"], item["last_sequence"]),
            reverse=True,
        )
    )


def _agent_values(events: tuple[TelemetryEvent, ...]) -> tuple[dict[str, Any], ...]:
    latest: dict[str, TelemetryEvent] = {}
    for item in events:
        if item.event_type is EventType.AGENT_SIGNAL_EMITTED:
            agent_id = getattr(item.payload, "agent_id", None)
            if isinstance(agent_id, str):
                latest[agent_id] = item
    return tuple(
        {
            "agent_id": key,
            "agent_version": value.payload.agent_version,  # type: ignore[union-attr]
            "latest_signal": value,
        }
        for key, value in sorted(latest.items())
    )


def _run_status(items: list[TelemetryEvent]) -> str:
    types = {item.event_type for item in items}
    if EventType.PIPELINE_FAILED in types:
        return "failed"
    if EventType.PIPELINE_COMPLETED in types or EventType.BACKTEST_COMPLETED in types:
        return "completed"
    return "running"


def _page(events: tuple[TelemetryEvent, ...], limit: int, offset: int) -> dict[str, Any]:
    return _page_values(events, limit, offset)


def _page_values(values: tuple[Any, ...], limit: int, offset: int) -> dict[str, Any]:
    return {
        "api_version": API_VERSION,
        "items": values[offset : offset + limit],
        "total": len(values),
        "limit": limit,
        "offset": offset,
    }


def _parse_event_types(value: str | None) -> frozenset[EventType] | None:
    if not value:
        return None
    try:
        return frozenset(EventType(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise ValueError("event_type contains an unsupported value") from error


def _enqueue_or_lag(
    queue: asyncio.Queue[TelemetryEvent | None], item: TelemetryEvent
) -> None:
    if queue.full():
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait(None)
        return
    queue.put_nowait(item)
