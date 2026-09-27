from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.models import Incident
from app.models.conversation import utc_now
from app.repositories.incidents import IncidentRepository
from app.schemas.incident import IncidentBroadcastResult, IncidentRead, IncidentUpdateRead
from app.services.incident_detection import (
    IncidentFingerprint,
    build_fingerprint,
    recompute_signature,
    similarity,
)


logger = logging.getLogger(__name__)


class IncidentNotFound(LookupError):
    pass


class IncidentConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class IncidentMatch:
    incident_id: str
    score: float
    evidence_tokens: list[str]


class IncidentService:
    def __init__(self, repository: IncidentRepository, *, threshold: float, min_cluster_size: int):
        self.repository = repository
        self.threshold = threshold
        self.min_cluster_size = min_cluster_size

    def read(self, incident_id: str) -> IncidentRead:
        incident = self.repository.get(incident_id)
        if incident is None:
            raise LookupError(incident_id)
        conversation_ids = self.repository.conversation_ids(incident.id)
        latest = incident.updates[-1] if incident.updates else None
        return IncidentRead(
            id=incident.id,
            status=incident.status,
            service=incident.service,
            title=incident.title,
            signature_tokens=list(incident.signature_tokens),
            similarity_threshold=incident.similarity_threshold,
            revision=incident.revision,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            conversation_count=len(conversation_ids),
            conversation_ids=conversation_ids,
            evidence_tokens=list(incident.signature_tokens),
            latest_update=IncidentUpdateRead.model_validate(latest) if latest else None,
        )

    def list_incidents(self, *, include_resolved: bool = False) -> list[IncidentRead]:
        incidents = self.repository.list_incidents(include_resolved=include_resolved)
        status_order = {"CANDIDATE": 0, "ACTIVE": 1, "RESOLVED": 2}
        items = [self.read(incident.id) for incident in incidents]
        return sorted(
            items,
            key=lambda item: (
                status_order[item.status.value],
                -item.conversation_count,
                -item.updated_at.timestamp(),
                item.id,
            ),
        )

    def list_open(self) -> list[IncidentRead]:
        return self.list_incidents()

    def broadcast(
        self,
        incident_id: str,
        message: str,
        request_key: str,
        expected_revision: int,
    ) -> IncidentBroadcastResult:
        incident = self.repository.get(incident_id)
        if incident is None:
            raise IncidentNotFound(incident_id)
        delivered_to = self.repository.conversation_ids(incident.id)
        if self.repository.find_update(incident.id, request_key) is not None:
            return IncidentBroadcastResult(
                incident=self.read(incident.id),
                delivered_to=delivered_to,
            )
        if incident.status == "RESOLVED":
            raise IncidentConflict("resolved incident cannot receive broadcasts")
        if incident.revision != expected_revision:
            raise IncidentConflict("incident changed; reload it before broadcasting")

        try:
            for conversation in self.repository.conversations(incident.id):
                self.repository.append_message(conversation, message)
            self.repository.create_update(
                incident,
                message=message,
                request_key=request_key,
            )
            if incident.status == "CANDIDATE":
                incident.status = "ACTIVE"
            incident.updated_at = utc_now()
            self.repository.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.repository.session.rollback()
            if self.repository.find_update(incident_id, request_key) is not None:
                return IncidentBroadcastResult(
                    incident=self.read(incident_id),
                    delivered_to=self.repository.conversation_ids(incident_id),
                )
            raise IncidentConflict("incident changed; reload it before broadcasting") from error
        except Exception:
            self.repository.session.rollback()
            raise

        logger.info(
            "incident.broadcast incident_id=%s request_key=%s delivery_count=%s",
            incident_id,
            request_key,
            len(delivered_to),
        )
        return IncidentBroadcastResult(
            incident=self.read(incident_id),
            delivered_to=delivered_to,
        )

    def match_first_turn(self, conversation_id: str) -> IncidentMatch | None:
        conversation = self.repository.get_conversation(conversation_id)
        if conversation is None or conversation.incident_id is not None:
            return None
        fingerprint = build_fingerprint(conversation)
        if fingerprint is None:
            return None
        match = self._best_open_result(fingerprint)
        if match is None:
            return None
        incident, score, evidence = match
        self.repository.link(conversation, incident)
        self._recompute_signature(incident)
        self.repository.session.flush()
        logger.info(
            "incident.conversation_linked incident_id=%s conversation_id=%s score=%s evidence=%s",
            incident.id,
            conversation.id,
            score,
            evidence,
        )
        return IncidentMatch(incident_id=incident.id, score=score, evidence_tokens=evidence)

    def observe_escalated(self, conversation_id: str) -> Incident | None:
        conversation = self.repository.get_conversation(conversation_id)
        if conversation is None or conversation.status != "ESCALATED":
            return None
        if conversation.incident_id:
            return self.repository.get(conversation.incident_id)
        fingerprint = build_fingerprint(conversation)
        if fingerprint is None:
            return None

        if match := self._best_open(fingerprint):
            self._link(match, conversation, fingerprint)
            return match

        candidates = []
        for item in self.repository.list_unlinked_escalated(fingerprint.service, conversation.id):
            other = build_fingerprint(item)
            if other is not None and similarity(fingerprint, other).score >= self.threshold:
                candidates.append((item, other))
        if len(candidates) + 1 < self.min_cluster_size:
            return None

        try:
            with self.repository.session.begin_nested():
                all_fingerprints = [fingerprint, *(item[1] for item in candidates)]
                incident = self.repository.create_candidate(
                    fingerprint.service,
                    f"Массовая недоступность {conversation.service or fingerprint.service}",
                    recompute_signature(all_fingerprints),
                    self.threshold,
                )
                for item, _ in candidates:
                    self.repository.link(item, incident)
                self.repository.link(conversation, incident)
                self._recompute_signature(incident)
                self.repository.session.flush()
        except IntegrityError:
            match = self._best_open(fingerprint)
            if match is None:
                logger.exception("incident.detection_failed conversation_id=%s", conversation.id)
                return None
            self._link(match, conversation, fingerprint)
            return match

        logger.info(
            "incident.cluster_created incident_id=%s member_count=%s",
            incident.id,
            len(candidates) + 1,
        )
        return incident

    def _best_open(self, fingerprint: IncidentFingerprint) -> Incident | None:
        result = self._best_open_result(fingerprint)
        return result[0] if result else None

    def _best_open_result(
        self, fingerprint: IncidentFingerprint
    ) -> tuple[Incident, float, list[str]] | None:
        scored = []
        for incident in self.repository.list_open(fingerprint.service):
            representative = self._incident_fingerprint(incident)
            result = similarity(fingerprint, representative)
            if result.score >= incident.similarity_threshold:
                scored.append((result.score, incident.id, incident, result.evidence_tokens))
        if not scored:
            return None
        score, _, incident, evidence = max(scored, key=lambda item: (item[0], item[1]))
        return incident, score, evidence

    def _incident_fingerprint(self, incident: Incident) -> IncidentFingerprint:
        fingerprints = [
            result for item in self.repository.conversations(incident.id)
            if (result := build_fingerprint(item)) is not None
        ]
        if fingerprints:
            weighted = {
                token: max(item.weighted_tokens.get(token, 0) for item in fingerprints)
                for token in set().union(*(item.weighted_tokens for item in fingerprints))
                if token in incident.signature_tokens
            }
        else:
            weighted = {
                token: 3 if token in incident.service.split() or any(char.isdigit() for char in token) else 2
                for token in incident.signature_tokens
            }
        return IncidentFingerprint(service=incident.service, weighted_tokens=weighted)

    def _link(
        self,
        incident: Incident,
        conversation,
        fingerprint: IncidentFingerprint,
    ) -> None:
        self.repository.link(conversation, incident)
        self._recompute_signature(incident)
        self.repository.session.flush()
        evidence = similarity(fingerprint, self._incident_fingerprint(incident)).evidence_tokens
        logger.info(
            "incident.conversation_linked incident_id=%s conversation_id=%s score_evidence=%s",
            incident.id,
            conversation.id,
            evidence,
        )

    def _recompute_signature(self, incident: Incident) -> None:
        fingerprints = [
            result for item in self.repository.conversations(incident.id)
            if (result := build_fingerprint(item)) is not None
        ]
        incident.signature_tokens = recompute_signature(fingerprints)
        incident.updated_at = utc_now()
