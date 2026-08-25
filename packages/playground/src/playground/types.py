from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_DECISIONS = {"continue", "satisfied", "give_up"}
DEFAULT_PERSONA_MODEL = "local/qwen3-14b"


@dataclass
class Persona:
    id: str
    name: str
    summary: str = ""
    context: str = ""
    source: str = ""
    preferences: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    goal: str = ""
    communication_style: str = ""
    dimensions: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = ""
    persona_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "context": self.context,
            "source": self.source,
            "preferences": list(self.preferences),
            "dislikes": list(self.dislikes),
            "constraints": list(self.constraints),
            "goal": self.goal,
            "communicationStyle": self.communication_style,
            "dimensions": dict(self.dimensions),
            "schemaVersion": self.schema_version,
            "personaPath": self.persona_path,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any], *, persona_path: str = "") -> "Persona":
        dimensions = d.get("dimensions")
        return cls(
            id=str(d.get("id") or d.get("persona_id") or "unknown"),
            name=str(d.get("name") or d.get("display_name") or d.get("persona_id") or "unknown"),
            summary=str(d.get("summary") or ""),
            context=str(d.get("context") or ""),
            source=str(d.get("source") or ""),
            preferences=list(d.get("preferences", [])),
            dislikes=list(d.get("dislikes", [])),
            constraints=list(d.get("constraints", [])),
            goal=str(d.get("goal") or ""),
            communication_style=str(
                d.get("communicationStyle", d.get("communication_style", ""))
            ),
            dimensions=dict(dimensions) if isinstance(dimensions, dict) else {},
            schema_version=str(d.get("schema_version", d.get("schemaVersion", "")) or ""),
            persona_path=str(persona_path or d.get("persona_path") or d.get("personaPath") or ""),
        )


@dataclass
class PlaygroundConfig:
    domain: str = ""
    application_id: str = "meal_planning_nutrition"
    application_context: str = ""
    engine: str = "gpt-4o-mini"
    persona_model: str = DEFAULT_PERSONA_MODEL
    ranker_mode: str = "native"
    resource_mode: str = "recai_resources"
    max_turns: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        application_context = self.application_context or self.domain
        domain = self.domain or application_context
        return {
            "applicationId": self.application_id,
            "applicationContext": application_context,
            "domain": domain,
            "engine": self.engine,
            "personaModel": self.persona_model,
            "rankerMode": self.ranker_mode,
            "resourceMode": self.resource_mode,
            "maxTurns": self.max_turns,
        }


@dataclass
class SimulatorTurn:
    message: str
    decision: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.decision not in _DECISIONS:
            raise ValueError("decision must be one of {}".format(sorted(_DECISIONS)))

    def to_dict(self) -> Dict[str, Any]:
        return {"message": self.message, "decision": self.decision, "note": self.note}


@dataclass
class PlaygroundTurn:
    turn_index: int
    user_message: str
    assistant_message: str
    structured_exposure: List[Dict[str, Any]] = field(default_factory=list)
    decision: str = "continue"
    duration_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turnIndex": self.turn_index,
            "userMessage": self.user_message,
            "assistantMessage": self.assistant_message,
            "structuredExposure": [dict(item) for item in self.structured_exposure],
            "decision": self.decision,
            "durationSeconds": self.duration_seconds,
        }


@dataclass
class Questionnaire:
    constraint_satisfaction: int
    constraint_rationale: str
    preference_satisfaction: int
    preference_rationale: str
    overall_rating: int
    rating_reason: str
    asked_useful_clarifying_questions: bool
    clarifying_notes: str
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    artifact_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "constraintSatisfaction": self.constraint_satisfaction,
            "constraintRationale": self.constraint_rationale,
            "preferenceSatisfaction": self.preference_satisfaction,
            "preferenceRationale": self.preference_rationale,
            "overallRating": self.overall_rating,
            "ratingReason": self.rating_reason,
            "askedUsefulClarifyingQuestions": self.asked_useful_clarifying_questions,
            "clarifyingNotes": self.clarifying_notes,
        }
        payload.update(dict(self.extra_fields))
        return payload

    def artifact_dict(self) -> Dict[str, Any]:
        if self.artifact_payload:
            return dict(self.artifact_payload)

        def _bucket(score: int) -> str:
            if score >= 4:
                return "yes"
            if score >= 3:
                return "partially"
            return "no"

        payload = {
            "needConstraintSatisfaction": _bucket(self.constraint_satisfaction),
            "personalPreferenceSatisfaction": _bucket(
                self.preference_satisfaction
            ),
            "overallExperienceRating": self.overall_rating,
            "reason": self.rating_reason
            or self.constraint_rationale
            or self.preference_rationale,
            "askedUsefulClarificationQuestions": self.asked_useful_clarifying_questions,
            "clarifyingNotes": self.clarifying_notes,
        }
        payload.update(dict(self.extra_fields))
        return payload


@dataclass
class MetricScores:
    num_turns: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numTurns": self.num_turns,
        }


@dataclass
class PlaygroundResult:
    config: PlaygroundConfig
    persona: Persona
    sut_description: str
    transcript: List[PlaygroundTurn]
    questionnaire: Questionnaire
    metric_scores: MetricScores
    created_at: str
    prompts: Dict[str, str] = field(default_factory=dict)
    usage: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "config": self.config.to_dict(),
            "persona": self.persona.to_dict(),
            "sutDescription": self.sut_description,
            "transcript": [t.to_dict() for t in self.transcript],
            "questionnaire": self.questionnaire.to_dict(),
            "metricScores": self.metric_scores.to_dict(),
            "createdAt": self.created_at,
            "prompts": dict(self.prompts),
        }
        if self.usage:
            payload["usage"] = dict(self.usage)
        return payload
