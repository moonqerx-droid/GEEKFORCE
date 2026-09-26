# Natural Dialogue Design

## Goal

Make HelpFlow sound attentive and contextual while keeping the deterministic playbook engine in control of safety, actions, escalation, and state transitions.

## Decisions

- `TriageEngine.decide()` first computes the same rule-owned `Decision` as today.
- When an LLM is configured, a response renderer receives only the immutable prepared message and action. It does not receive the conversation history or collected facts a second time.
- The renderer may only rewrite the user-facing message. It cannot change `action`, `question`, `step`, escalation team, status, or safety notice.
- LLM output is strict JSON with one `message` field. Blank, malformed, oversized, or failed output falls back to the original deterministic message.
- Prompts require concise Russian, avoid invented facts, avoid claims that an action already succeeded, and preserve mandatory safety text verbatim.
- Rule-only mode remains fully functional. Existing API contracts do not change.
- Debug observability is recorded in the decision as `message_source` (`rules` or `llm`) without exposing prompts or secrets.

## Acceptance Criteria

1. A valid LLM rewrite changes only `message` and reports `message_source=llm`.
2. Actions and structured decision fields are identical with and without rewriting.
3. Failures, malformed JSON, blank messages, or messages above 1200 characters use the rules fallback.
4. Safety notices remain present even if the model omits them.
5. The response-rendering prompt does not contain user messages or collected facts.
6. Existing rule-only and API tests remain green.
