# Incident Radar — design specification

Date: 2026-09-26  
Status: proposed for implementation  
Scope: backend MVP for the hackathon demo

## Outcome

Incident Radar identifies repeated support requests, groups them into a possible mass incident, stops redundant diagnosis for later matching requests, and lets an operator send one update to every linked conversation.

The demo success path is deterministic and works without an LLM or network access:

1. Three similar escalated CRM requests form an incident candidate.
2. A fourth matching request is linked during its first turn.
3. The fourth user is told that a mass issue is already being investigated.
4. The operator sees the incident and all linked conversations.
5. One broadcast appears in every linked conversation.

## Constraints

- SQLite remains the only database for the MVP.
- Existing conversation endpoints and enum values remain compatible.
- Detection must produce the same result on macOS, Windows, CI, and Docker.
- No embeddings, external API, background worker, or message broker are required.
- The current `conversation.incident_id` field remains the membership link.
- Operator authentication remains outside this local-demo scope.

## Approaches considered

### Selected: deterministic token similarity

Normalize service, summary, symptoms, and the original request; remove common Russian stop words; calculate a weighted Jaccard score. Require a compatible service and a configurable similarity threshold.

This is explainable in the operator UI, cheap to test, and independent of network availability. It is the appropriate hackathon MVP.

### Deferred: embeddings

Embeddings improve paraphrase matching but add model downloads or an external provider, latency, platform differences, and less predictable demo behavior.

### Rejected for detection: direct LLM classification

An LLM-only detector is difficult to reproduce and test. The LLM may later enrich an incident summary, but it must not decide membership.

## Domain model

### Incident

- `id`: UUID string.
- `status`: `CANDIDATE`, `ACTIVE`, or `RESOLVED`.
- `service`: normalized service shared by the cluster.
- `title`: operator-facing description.
- `signature_tokens`: JSON list used for comparison and explanation.
- `similarity_threshold`: threshold captured when the cluster was created.
- `revision`: optimistic concurrency version.
- `created_at`, `updated_at`.

An automatically detected cluster starts as `CANDIDATE`. Broadcasts are allowed for candidates in the MVP because the operator action itself confirms that the event is meaningful. The first broadcast changes it to `ACTIVE`.

### IncidentUpdate

- `id`: integer primary key.
- `incident_id`: foreign key with cascade delete.
- `message`: text sent to linked users.
- `created_at`.
- `request_key`: client-generated idempotency key unique within the incident.

### Conversation membership

`Conversation.incident_id` stores the incident UUID. A conversation belongs to at most one incident. The existing column has no database foreign key, and the migration will not rebuild the legacy SQLite table merely to add one. Repository methods validate the referenced incident. `IncidentUpdate.incident_id` does use a database foreign key because that table is new.

## Detection input

The detector builds a fingerprint from:

- normalized `service`;
- `summary`;
- `symptoms`;
- original user request;
- stable facts such as `error_text`.

Normalization lowercases text, replaces `ё` with `е`, extracts letter/digit tokens, removes stop words, and discards one-character tokens. Error codes and product names remain significant.

Service compatibility is mandatory. Exact normalized service names match. `Не определён` never creates a cluster. Security incidents are excluded from similarity clustering because they require individual handling. Explicit `mass_incident` playbook requests may create or join a cluster but still use the same deterministic membership rules.

Similarity uses weighted Jaccard:

- service tokens weight 3;
- error codes weight 3;
- summary and symptom tokens weight 2;
- remaining request tokens weight 1.

The default threshold is `0.55`, configured as `INCIDENT_SIMILARITY_THRESHOLD`. Cluster creation requires `INCIDENT_MIN_CLUSTER_SIZE`, default `3`.

## Detection flow

### After an escalation

1. Build the conversation fingerprint.
2. Compare it with open incidents of the same service.
3. If the best score meets the threshold, link the conversation.
4. Otherwise compare it with unlinked, escalated conversations of the same service.
5. If the current conversation plus matching candidates reaches the minimum size, create one incident and link the group atomically.

### During the first turn of a new request

After triage has identified service and symptoms, compare the request with existing `CANDIDATE` and `ACTIVE` incidents. A qualifying match:

- links the conversation;
- changes it to `ESCALATED` without executing further troubleshooting steps;
- creates an escalation card describing the incident match;
- appends one assistant message saying that a possible mass incident is already being investigated.

The response therefore immediately contains `incident_id`, `ESCALATED`, and the notification. Detection runs after analysis fields are filled but before the normal dialogue decision is written, so the unused troubleshooting question never enters message history.

### Cluster signature updates

When a conversation joins, the incident signature becomes the union of significant tokens shared by at least half of linked conversations plus service and error-code tokens. This prevents one unusual request from permanently broadening the cluster.

## API

### `GET /api/operator/incidents`

Returns candidates and active incidents ordered by status, linked conversation count descending, then update time descending.

Each item includes:

- incident fields and `revision`;
- `conversation_count`;
- `conversation_ids`;
- latest update, if any;
- `evidence_tokens` for a judge-friendly explanation of why requests were grouped.

Resolved incidents are excluded unless `include_resolved=true`.

### `POST /api/operator/incidents/{incident_id}/broadcast`

Request:

```json
{
  "message": "Наблюдаем массовую недоступность CRM. Команда уже работает над восстановлением.",
  "request_key": "demo-update-1",
  "expected_revision": 2
}
```

Behavior:

- validate message length `1..1000` after trimming;
- reject a stale revision with `409`;
- if the same `request_key` already exists, return the existing result without duplicating messages;
- add one assistant message to each linked conversation;
- store one `IncidentUpdate`;
- change `CANDIDATE` to `ACTIVE`;
- update incident and conversation revisions in one transaction.

The response returns the updated incident and `delivered_to` conversation IDs.

### Existing conversation responses

`ConversationRead.incident_id` already exposes membership. No existing field is renamed or removed.

## Module boundaries

- `app/models/incident.py`: persistence models only.
- `app/schemas/incident.py`: HTTP contracts only.
- `app/repositories/incidents.py`: database queries and membership writes.
- `app/services/incidents.py`: normalization, similarity, clustering, and broadcast orchestration.
- `app/api/routes/operator.py`: thin HTTP mapping and error translation.
- dialogue integration calls the service at two explicit points: after first-turn analysis but before the next dialogue decision, and after escalation state is prepared but before commit.

The detector does not import FastAPI, templates, or the AI client. The dialogue service does not implement similarity logic.

## Transactions and concurrency

- Cluster creation, membership changes, notification messages, and broadcasts are transactional.
- `Incident.revision` uses SQLAlchemy optimistic concurrency control.
- Conversation revisions are touched whenever radar adds membership or a message.
- `IncidentUpdate(incident_id, request_key)` has a unique constraint for broadcast idempotency.
- A race that attempts to create equivalent clusters is handled by re-reading open incidents and retrying membership once inside the request; arbitrary retries are not performed. If the retry also loses, the dialogue still commits without radar membership and the failure is logged.

SQLite production for the demo runs as one API container. The design remains correct under multiple threads. Moving to multi-process production would require PostgreSQL or an explicit SQLite write lock strategy.

## Operator debug UI

The existing `/debug/operator` page gains an Incident Radar section above the ticket queue:

- candidate/active badge;
- service and title;
- number of linked requests;
- evidence tokens;
- latest broadcast;
- message field and broadcast button.

The page remains a dependency-free local diagnostic interface. The teammate's future operator app can consume the same endpoints.

## Error handling

- Missing incident: `404`.
- Resolved incident broadcast: `409`.
- Stale revision: `409` with instruction to reload.
- Invalid message or request key: `422`.
- No matching incident is normal and does not change the conversation.
- Detection is advisory. A detector exception is caught before dialogue commit, its pending radar changes are discarded, and the normal dialogue decision continues. The failure is logged for operator visibility; a support request must not fail merely because clustering is unavailable.

## Observability

Structured log events:

- `incident.cluster_created` with incident ID and member count;
- `incident.conversation_linked` with score and evidence tokens;
- `incident.broadcast` with request key and delivery count;
- `incident.detection_failed` with conversation ID and error class.

Logs contain no API keys and do not repeat full user messages.

## Test strategy

Unit tests:

- normalization and weighted similarity;
- service mismatch and unknown-service exclusion;
- threshold boundary;
- signature recomputation.

Repository/service tests with SQLite:

- three similar escalated requests form exactly one candidate;
- unrelated services remain separate;
- a fourth first-turn request joins and stops diagnosis;
- membership remains unique under repeated observation;
- a broadcast reaches every linked conversation once;
- replayed `request_key` is idempotent;
- stale revision and concurrent broadcast produce one winner;
- transaction rollback prevents partial messages.

API acceptance test:

- seed three CRM failures;
- submit a fourth request;
- verify `ESCALATED` and `incident_id`;
- list the incident;
- broadcast an update;
- retrieve all four conversations and verify the update.

Docker smoke test verifies the migration, both endpoints, and the same four-request path.

## Deferred work

- embeddings and semantic reranking;
- automatic incident resolution;
- email, push, or Telegram delivery;
- operator authentication and audit identities;
- cross-tenant isolation;
- PostgreSQL advisory locks;
- analytics dashboards.
