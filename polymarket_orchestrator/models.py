from __future__ import annotations

from pydantic import BaseModel, Field


class Token(BaseModel):
    token_id: str
    outcome: str
    price: float = 0.0


class Market(BaseModel):
    id: str
    question: str
    description: str = ""
    outcomes: list[str] = Field(default_factory=list)
    tokens: list[Token] = Field(default_factory=list)
    end_date: str = ""
    volume: float = 0.0
    liquidity: float = 0.0

    @property
    def yes_price(self) -> float:
        for token in self.tokens:
            if token.outcome.lower() == "yes":
                return token.price
        return self.tokens[0].price if self.tokens else 0.0

    @property
    def summary(self) -> str:
        prices = ", ".join(f"{t.outcome}: {t.price:.1%}" for t in self.tokens)
        return f"{self.question} [{prices}]"


class AgentOpinion(BaseModel):
    agent_name: str
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str
    confidence: str = "medium"  # low, medium, high


class DebateResult(BaseModel):
    market: Market
    opinions: list[AgentOpinion]
    consensus_probability: float = Field(ge=0.0, le=1.0)
    synthesis_reasoning: str


class BettingAlert(BaseModel):
    market: Market
    polymarket_probability: float
    ai_probability: float
    divergence: float
    recommended_side: str  # "YES" or "NO"
    reasoning: str

    @property
    def divergence_pct(self) -> str:
        return f"{self.divergence:+.1%}"
