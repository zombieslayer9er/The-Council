# Local Freqtrade Docker boundary

Freqtrade runs as an external, disposable backtest process. It does not import the
Council, receive provider credentials, expose an API, or remain running after a command.
A separate data-only service makes historical acquisition an explicit step before a
recorded backtest. The backtest service has outbound network access because Freqtrade
loads public exchange market metadata at startup even when candle data and fees are
provided locally. It receives no exchange credentials and cannot submit live orders.

The image defaults to the versioned `freqtradeorg/freqtrade:2026.8` tag. Override
`FREQTRADE_IMAGE` with an approved tag or digest deliberately; never use `latest` or
`develop` for recorded research. The engine records Freqtrade's reported version and
hashes its effective configuration and exported artifact.

## Host prerequisite

Enable hardware virtualization in BIOS/UEFI, then install and start Docker Desktop with
its WSL 2 backend and Compose plugin. `Docker.sbx` is Docker's AI
agent sandbox product and is not a replacement for the host Docker Compose workflow used
here. On Windows, Freqtrade's documentation recommends rebooting after Docker Desktop is
first installed.

Then verify and pull the pinned image:

```powershell
.\tools\setup-freqtrade-docker.ps1
```

The setup script performs only an engine readiness check, image pull, and disposable
`freqtrade --version` probe. It also creates the ignored local `user_data` mount required
by Freqtrade. It never starts trading.

## Download immutable input data

Download a closed historical interval through the data service and then record the
resulting directory's content identity as the request's `dataset_id`:

```powershell
$env:BOTNET_COUNCIL_WORKSPACE = (Resolve-Path .).Path
docker compose --project-directory integrations/freqtrade `
  --file integrations/freqtrade/compose.yaml run --rm --no-deps -T freqtrade-data `
  download-data --exchange kraken --pairs BTC/USD --timeframes 5m `
  --timerange 20260101-20260201 --dl-trades `
  --datadir /workspace/integrations/freqtrade/user_data/data/kraken
```

Downloaded data is runtime state and is ignored by Git. Do not download while a replay
is running, and do not reuse a `dataset_id` after any file changes.

## Supply Council signals

Use `CouncilDecisionStrategyAdapter.write_signal_artifact` to export frozen decisions to
`integrations/freqtrade/user_data/signals/council-signals.json`. The standalone
`CouncilSignalStrategy` checks adapter identity/version, timestamp awareness, field
types, and duplicate pair/timestamp rows. The adapter requires the exact source candle's
open timestamp for every decision; substituting the decision/close timestamp would move
execution one candle late. The strategy uses only exact candle timestamps and does not
compute signals from future rows. Because the hardened engine permits spot mode only,
short entries are ignored while short/flat decisions can still close a long position.

Copy `integrations/freqtrade/request.example.json`, replace its dataset identity and
closed timerange, and run:

```powershell
botnet-council freqtrade-backtest `
  --request integrations/freqtrade/request.example.json `
  --docker-compose integrations/freqtrade/compose.yaml `
  --workspace-root .
```

The Docker runner rejects the request if its data, strategy, signal, artifact, or working
paths resolve outside the mounted workspace. The engine forces `dry_run: true`, spot
mode, an offline database, disabled API/Telegram settings, and off-exchange stop losses.
The container also runs read-only with all Linux capabilities dropped. It never falls
back to the internal simulator.

Lookahead and recursive checks use the same isolated path:

```powershell
botnet-council freqtrade-backtest --request request.json `
  --docker-compose integrations/freqtrade/compose.yaml --validation lookahead
botnet-council freqtrade-backtest --request request.json `
  --docker-compose integrations/freqtrade/compose.yaml --validation recursive
```
