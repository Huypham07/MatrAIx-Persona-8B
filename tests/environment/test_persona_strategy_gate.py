"""Unit tests for persona_strategy.json CI validation helpers."""

from __future__ import annotations

import json
from pathlib import Path


def test_validate_persona_strategy_requires_file(tmp_path: Path) -> None:
    from backend.service.persona_strategy import validate_persona_strategy_file

    errors = validate_persona_strategy_file(tmp_path)
    assert any("missing required persona_strategy.json" in err for err in errors)


def test_validate_persona_strategy_requires_cohort(tmp_path: Path) -> None:
    from backend.service.persona_strategy import validate_persona_strategy_file

    (tmp_path / "persona_strategy.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "sampling": {"mode": "random", "sampleSize": 4},
                "dimensionFilters": {},
            }
        ),
        encoding="utf-8",
    )
    errors = validate_persona_strategy_file(tmp_path, require_cohort=True)
    assert any("target cohort" in err for err in errors)

    errors_relaxed = validate_persona_strategy_file(tmp_path, require_cohort=False)
    assert errors_relaxed == []


def test_validate_persona_strategy_stratified_needs_axes(tmp_path: Path) -> None:
    from backend.service.persona_strategy import validate_persona_strategy_file

    (tmp_path / "persona_strategy.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "sampling": {
                    "mode": "stratified",
                    "allocation": "equalTotal",
                    "sampleSize": 4,
                },
                "dimensionFilters": {"region": ["Oceania"]},
            }
        ),
        encoding="utf-8",
    )
    errors = validate_persona_strategy_file(tmp_path)
    assert any("sampling.fields" in err for err in errors)


def test_normalize_persona_strategy_preserves_pinned_segments() -> None:
    from backend.service.persona_strategy import normalize_persona_strategy

    strategy = normalize_persona_strategy(
        {
            "schemaVersion": "1.1",
            "pool": "persona/datasets/sample",
            "segments": [
                {
                    "id": "careful",
                    "label": "Careful shoppers",
                    "hypothesis": "They should resist a price increase.",
                    "dimensions": {"risk_tolerance": ["Cautious", "Risk-averse"]},
                    "personaIds": ["0001", "0002"],
                },
                {
                    "id": "premium",
                    "label": "Premium shoppers",
                    "hypothesis": "They should prioritize quality.",
                    "dimensions": {"economic_motivation": ["Premium-seeking"]},
                    "personaIds": ["0003", "0004"],
                },
            ],
            "sampling": {"mode": "pinnedSegments", "personasPerSegment": 2},
        }
    )

    assert strategy["sampling"] == {
        "mode": "pinnedSegments",
        "personasPerSegment": 2,
    }
    assert [segment["id"] for segment in strategy["segments"]] == [
        "careful",
        "premium",
    ]
    assert strategy["personaIds"] == ["0001", "0002", "0003", "0004"]


def test_validate_pinned_segments_against_raw_personas(tmp_path: Path) -> None:
    from backend.service.persona_strategy import validate_persona_strategy_file

    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "demo"
    pool_dir = repo / "persona" / "datasets" / "sample"
    task_dir.mkdir(parents=True)
    pool_dir.mkdir(parents=True)
    for persona_id, language, risk in (
        ("0001", "Spanish", "Cautious"),
        ("0002", "Mandarin", "Risk-averse"),
    ):
        (pool_dir / f"persona_{persona_id}.yaml").write_text(
            json.dumps(
                {
                    "persona_id": persona_id,
                    "dimensions": {
                        "region": "Test region",
                        "primary_language": language,
                        "risk_tolerance": risk,
                    },
                }
            ),
            encoding="utf-8",
        )
    (task_dir / "persona_strategy.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.1",
                "pool": "persona/datasets/sample",
                "segments": [
                    {
                        "id": "careful",
                        "label": "Careful users",
                        "hypothesis": "They proceed cautiously.",
                        "dimensions": {
                            "risk_tolerance": ["Cautious", "Risk-averse"]
                        },
                        "personaIds": ["0001", "0002"],
                    }
                ],
                "sampling": {
                    "mode": "pinnedSegments",
                    "personasPerSegment": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    assert validate_persona_strategy_file(task_dir, repo_root=repo) == []


def test_validate_pinned_segments_rejects_duplicates_and_dimension_mismatch(
    tmp_path: Path,
) -> None:
    from backend.service.persona_strategy import validate_persona_strategy_file

    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "demo"
    pool_dir = repo / "persona" / "datasets" / "sample"
    task_dir.mkdir(parents=True)
    pool_dir.mkdir(parents=True)
    for persona_id in ("0001", "0002", "0003"):
        (pool_dir / f"persona_{persona_id}.yaml").write_text(
            json.dumps(
                {
                    "persona_id": persona_id,
                    "dimensions": {
                        "region": "Test region",
                        "primary_language": "English",
                        "risk_tolerance": "Balanced",
                    },
                }
            ),
            encoding="utf-8",
        )
    (task_dir / "persona_strategy.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.1",
                "pool": "persona/datasets/sample",
                "segments": [
                    {
                        "id": "one",
                        "label": "One",
                        "hypothesis": "First group.",
                        "dimensions": {"risk_tolerance": ["Cautious"]},
                        "personaIds": ["0001", "0002"],
                    },
                    {
                        "id": "two",
                        "label": "Two",
                        "hypothesis": "Second group.",
                        "dimensions": {"risk_tolerance": ["Balanced"]},
                        "personaIds": ["0002", "0003"],
                    },
                ],
                "sampling": {
                    "mode": "pinnedSegments",
                    "personasPerSegment": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    errors = validate_persona_strategy_file(task_dir, repo_root=repo)
    assert any("reused across segments" in error for error in errors)
    assert any("risk_tolerance" in error and "Cautious" in error for error in errors)
