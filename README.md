# Botnet Council

A deliberately small Python scaffold for modular market research and **paper-only**
execution. The core protocol is independent of model providers, agent frameworks,
exchanges, and Freqtrade.

> This repository is engineering scaffolding, not investment advice. It contains no
> live-trading mode, exchange client, credential schema, or promise of profitability.

## Architecture

```text
MarketDataProvider
        |
        v
SpecialistAgent[]  -- deterministic / statistical / ML / local LLM / hosted agent
        |
        v
AgentSignal v1.1 (validated, snapshot-bound, provider-neutral)
        |
        v
DeterministicCouncil -> CouncilDecision
        |
        v
DeterministicRiskGovernor -- absolute veto authority
        |
        +-- veto --------------------------------------> no execution
        |
        v
ApprovedOrder (paper_only=True, NEXT_BAR_OPEN, bounded costs)
        |
        v
ExecutionAdapter -> atomic PaperExecutionAdapter / Freqtrade adapter boundary
```

Only the composition layer (`pipeline.py`) sees every stage. Specialists receive
market data and non-secret context—not brokers, execution adapters, API keys, or
exchange credentials. Execution accepts an `ApprovedOrder`, which is emitted only
after deterministic risk checks. Pydantic provides strict validation for all shared
boundary contracts.

## Included

- A common `SpecialistAgent` protocol and versioned, snapshot-bound `AgentSignal` schema.
- Typed historical OHLCV requests, explicit candle availability, a read-only Kraken
  Spot adapter, quality/gap reports, and a provenance-preserving Parquet cache.
- Simple deterministic Trend, Mean Reversion, Seasonality, Volatility, and Regime specialists.
- An order-independent weighted council. Only alpha signals vote directionally;
  volatility and regime signals remain attached as risk/research evidence.
- Timestamped mark-to-market accounting with separate average entry and current mark,
  validated equity, cost basis, and unrealized PnL.
- A deterministic risk governor with causal-time, confidence, observation freshness,
  symbol, shorting, typed volatility, bounded-cost, cash, position, and exposure checks.
- Explicit target, abstention, no-action, and reduce-only semantics so restrictions do
  not trap exposure that a trade would strictly reduce.
- An atomic in-memory simulator with bounded fees/slippage and causal next-bar-open fills.
- A pure Freqtrade DTO translator restricted to `dry_run` and `backtest` modes.
- Typed TOML configuration, structured JSON logging, tests, and extension guides.
- A deterministic, event-driven single-instrument historical backtester with Kraken
  input, strict coverage checks, causal next-open fills, JSON summaries, and Parquet ledgers.
- A versioned, read-only telemetry boundary with ordered in-process pub/sub, REST/WebSocket
  observation, causal replay IDs, and generated TypeScript contracts. See
  [`docs/telemetry-api.md`](docs/telemetry-api.md).

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
python -m botnet_council
python -m botnet_council backtest --start 2026-09-08T20:00:00Z --end 2026-09-08T23:00:00Z
```

The demo uses generated bars and an in-memory paper account. Configuration lives in
[`config/default.toml`](config/default.toml). No `.env` or credential fields are
needed or supported.

### Telemetry dashboard

Run the API and web console in separate terminals:

```bash
botnet-council-api
cd web
pnpm install
pnpm dev
```

Open `http://127.0.0.1:5173`. Vite proxies the versioned REST API and read-only
WebSocket stream to `127.0.0.1:8000`. The dashboard never submits orders or mutates
domain state; it renders only telemetry emitted by the API process.

## Extension points

Implement `SpecialistAgent.analyze(snapshot, context) -> AgentSignal` for a new
specialist. An OpenAI Agents SDK wrapper or local-model wrapper belongs inside an
agent implementation and must convert provider output into a validated
`AgentSignal`; the council protocol does not change.

Implement `MarketDataProvider` and `HistoricalMarketDataProvider` for historical files
or a read-only market feed.
Implement `ExecutionAdapter` only for simulation. Freqtrade-specific code belongs
under `adapters/`; see [`docs/extending.md`](docs/extending.md).
Kraken timestamp and cache semantics are documented in
[`docs/market-data.md`](docs/market-data.md).
The fixed-hypothesis calendar matcher and its causal restrictions are documented in
[`docs/seasonality.md`](docs/seasonality.md).

## Repository map

```text
config/                         runtime policy, never secrets
src/botnet_council/
  agents/                       provider-neutral specialists
  council/                      deterministic aggregation
  risk/                         deterministic veto and sizing
  execution/                    paper-only execution contract and simulator
  market_data/                  read-only market data contract
  adapters/                     external-framework translation boundaries
  telemetry/                    public event contracts, serializers, store, and publisher
  api/                          optional read-only FastAPI and WebSocket boundary
  schemas.py                    immutable cross-module contracts
  pipeline.py                   composition root
tests/                          unit and boundary tests
docs/                           architecture and extension notes
web/                            React telemetry console
```

## Non-goals for this scaffold

- Real-money execution, exchange authentication, secret management, or live orders.
- Autonomous access from an AI/LLM component to an account or broker.
- Production persistence or portfolio optimizer.
- Coupling the domain model to Freqtrade or any agent framework.
