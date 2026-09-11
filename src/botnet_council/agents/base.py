"""The stable extension point for deterministic, ML, local-LLM, or hosted agents."""

from typing import Protocol, runtime_checkable

from botnet_council.schemas import AgentContext, AgentSignal, MarketSnapshot, SignalType


@runtime_checkable
class SpecialistAgent(Protocol):
    """Provider-neutral specialist interface.

    Implementations receive market data plus non-secret context and return one
    validated signal. They never receive execution adapters or credentials.
    """

    @property
    def agent_id(self) -> str: ...

    @property
    def signal_type(self) -> SignalType: ...

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal: ...


def warmup_bars(agent: SpecialistAgent) -> int:
    """Return an agent's declared history requirement without widening its protocol."""
    value = getattr(agent, "warmup_bars", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"agent {agent.agent_id!r} has an invalid warmup_bars declaration")
    return value
