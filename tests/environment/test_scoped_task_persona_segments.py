from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_SEGMENT_COUNTS = {
    "chat_meal-planning-nutrition": 4,
    "survey_price-sensitivity-hasbro-gaming-candy-land": 3,
    "survey_annual-checkup-habits": 4,
    "example-survey_product-feedback": 3,
}


def test_scoped_tasks_have_valid_task_specific_pinned_segments() -> None:
    from backend.service.persona_strategy import validate_persona_strategy_file

    observed_counts: set[int] = set()
    for task_name, expected_count in EXPECTED_SEGMENT_COUNTS.items():
        task_dir = REPO_ROOT / "application" / "tasks" / task_name
        payload = json.loads((task_dir / "persona_strategy.json").read_text())

        assert payload["sampling"] == {
            "mode": "pinnedSegments",
            "personasPerSegment": 2,
        }
        assert len(payload["segments"]) == expected_count
        assert all(len(segment["personaIds"]) == 2 for segment in payload["segments"])
        assert validate_persona_strategy_file(task_dir, repo_root=REPO_ROOT) == []
        observed_counts.add(expected_count)

    assert len(observed_counts) > 1, "segment count must be inferred per task"


def test_scoped_surveys_have_required_narrative_free_text_questions() -> None:
    survey_tasks = [
        "survey_price-sensitivity-hasbro-gaming-candy-land",
        "survey_annual-checkup-habits",
        "example-survey_product-feedback",
    ]
    for task_name in survey_tasks:
        path = REPO_ROOT / "application" / "tasks" / task_name / "input" / "questionnaire.yaml"
        questionnaire = yaml.safe_load(path.read_text())
        narrative = [
            question
            for question in questionnaire["questions"]
            if question.get("type") == "free_text"
            and question.get("responseStyle") == "narrative"
        ]
        assert narrative, f"{task_name} must have a narrative free_text question"
        assert all(question.get("required") is True for question in narrative)
