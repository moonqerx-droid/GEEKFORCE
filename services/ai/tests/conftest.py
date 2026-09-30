from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpflow_ai import (  # noqa: E402
    ConversationContext,
    DecisionAction,
    KnowledgeBase,
    StepOutcome,
    StepRecord,
    TriageEngine,
)


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


@pytest.fixture()
def engine(kb) -> TriageEngine:
    return TriageEngine(kb)


class DialogueSimulator:
    """Plays the backend role: keeps context and feeds the engine."""

    def __init__(self, engine: TriageEngine, first_message: str):
        self.engine = engine
        self.analysis = engine.analyze(first_message)
        self.ctx = ConversationContext(
            original_request=first_message,
            messages=[{"role": "user", "content": first_message}],
            known_facts=self.analysis.known_facts,
            playbook_id=self.analysis.recommended_playbook,
            urgency=self.analysis.urgency,
        )
        self.decision = self._decide()

    def _decide(self):
        decision = self.engine.decide(self.ctx)
        if decision.remember:
            self.ctx = self.ctx.model_copy(update={"known_facts": {**self.ctx.known_facts, **decision.remember}})
        if decision.action == DecisionAction.ASK:
            self.ctx = self.ctx.model_copy(
                update={"asked_facts": [*self.ctx.asked_facts, decision.question.fact]}
            )
        return decision

    def answer(self, text: str):
        facts = self.engine.absorb_answer(text, self.ctx)
        self.ctx = self.ctx.model_copy(update={
            "known_facts": {**self.ctx.known_facts, **facts},
            "messages": [*self.ctx.messages, {"role": "user", "content": text}],
        })
        self.decision = self._decide()
        return self.decision

    def step_result(self, outcome: StepOutcome):
        assert self.decision.action.value == "step", self.decision
        record = StepRecord(step_id=self.decision.step.id, outcome=outcome)
        self.ctx = self.ctx.model_copy(update={
            "completed_steps": [*self.ctx.completed_steps, record],
            "verification_failed": False,
        })
        self.decision = self._decide()
        return self.decision

    def verify(self, text: str):
        assert self.decision.action.value == "verify", self.decision
        solved = self.engine.interpret_confirmation(text)
        if solved:
            return True
        self.ctx = self.ctx.model_copy(update={"verification_failed": True})
        self.decision = self._decide()
        return False


@pytest.fixture()
def simulate(engine):
    return lambda message: DialogueSimulator(engine, message)
