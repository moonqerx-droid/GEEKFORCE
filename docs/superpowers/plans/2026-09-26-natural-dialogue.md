# Natural Dialogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe, natural LLM wording to deterministic HelpFlow dialogue decisions.

**Architecture:** Rules create the canonical typed decision. An optional renderer can rewrite only its message, with schema validation, safety-text restoration, length limits, and deterministic fallback.

**Tech Stack:** Python 3.12, Pydantic 2, existing OpenAI-compatible `LLMClient`, pytest

**Spec:** `docs/superpowers/specs/2026-09-26-natural-dialogue-design.md`

## Global Constraints

- Rules retain ownership of actions, steps, questions, escalation, and safety.
- Rule-only mode must work with no network and no API key.
- The response renderer must not receive user messages or collected facts.
- Public API fields remain backward compatible.

## Review Focus

- Prompt injection in the latest message: user content is not sent to the response renderer at all.
- Blank/malformed/oversized model output: deterministic message is returned.
- Model omits a safety warning: mandatory safety notice is restored.
- LLM mutates the returned JSON after validation: only the `message` key is consumed.
- Repeated API latency: exactly one optional rewrite call per decision and existing client timeout/retry policy applies.

---

### Task 1: Safe Response Renderer

**Files:**
- Modify: `services/ai/helpflow_ai/schemas.py`
- Modify: `services/ai/helpflow_ai/prompts.py`
- Modify: `services/ai/helpflow_ai/engine.py`
- Modify: `services/ai/tests/test_llm.py`
- Modify: `services/ai/tests/test_dialogue_flow.py`

**Interfaces:**
- Consumes: `LLMClient.chat_json(system: str, user: str) -> dict`, `Decision`, `ConversationContext`, and `Playbook.safety_notice`.
- Produces: `Decision.message_source: Literal["rules", "llm"]` and `TriageEngine.decide()` with safe optional rewriting.

- [ ] **Step 1: Write failing renderer tests**

Cover a valid rewrite, unchanged action/question/step, blank and oversized fallback, transport failure fallback, safety notice restoration, and omission of user content from the rendering prompt.

- [ ] **Step 2: Verify RED**

Run: `cd services/ai && pytest tests/test_llm.py tests/test_dialogue_flow.py -q`
Expected: FAIL because decisions have no `message_source` and `decide()` does not call the renderer.

- [ ] **Step 3: Implement minimal safe rendering**

Add prompt builders, a `message_source` field defaulting to `rules`, split deterministic decision selection into `_decide_rules`, and add `_render_decision` that accepts only a trimmed `message` of 1–1200 characters and prepends a missing safety notice.

- [ ] **Step 4: Verify GREEN**

Run: `cd services/ai && pytest tests/test_llm.py tests/test_dialogue_flow.py -q && pytest -q`
Expected: all AI tests pass.

- [ ] **Step 5: Verify API integration**

Run: `cd apps/api && pytest -q`
Expected: all API tests pass with unchanged response contracts.

- [ ] **Step 6: Commit**

Run: `git add services/ai docs/superpowers && git commit -m "feat: add safe natural dialogue rendering"`
