# Research dashboard

The React console is an observational projection of the API. It does not run agents, generate
sample market data, start experiments, promote weights, or call providers. Empty and unavailable
states stay explicit so absence is never rendered as a neutral signal or zero.

## Views and authority

- **Live Council** projects the current generation-scoped event stream.
- **Evidence** joins `market_context_ready` with validated specialist signals and shows the
  Historical Recurrence analogue paths from signal metadata.
- **Learning** compares immutable weight generations and displays joined Librarian proposals and
  Teacher decisions.
- **Outcomes** reads persisted blind experiments and experience episodes. Oracle and Judge data
  are requested only when the experiment summary advertises the corresponding lifecycle gate.
- **History** remains isolated replay: loading an older run does not mutate live stream state.

All REST and WebSocket bodies pass runtime validation before they enter UI state. Types are
generated from Pydantic contracts in `contracts/typescript/types.generated.ts`. A malformed body,
sequence gap, or stream-generation change causes an explicit error or bootstrap reconciliation;
the UI does not partially apply untrusted data.

## Store configuration

Set `BOTNET_COUNCIL_EXPERIENCE_STORE` and `BOTNET_COUNCIL_WEIGHT_STORE` on the API process to
enable the experience replay and learning views. `/api/health` advertises those read capabilities
only when configured. The UI has no POST client and cannot promote, roll back, or otherwise
mutate these stores.
