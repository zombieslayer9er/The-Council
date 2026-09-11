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
