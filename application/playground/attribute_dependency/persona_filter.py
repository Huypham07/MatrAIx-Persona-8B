"""Persona Attribute Filter and Pruner based on Task Attribute Dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from .constants import REPO_ROOT

CORE_DEMOGRAPHIC_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "age_bracket",
        "gender_identity",
        "country_name",
        "region_name",
        "education_level",
        "household_income_band",
        "occupation",
        "employment_status",
    }
)


def find_task_attribute_dependencies_path(
    task_path: Optional[Union[str, Path]] = None,
    instrument_id: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Optional[Path]:
    """Locate the attribute_dependencies.json file for a given task or instrument."""
    repo = repo_root or REPO_ROOT
    candidates: List[Path] = []

    if task_path:
        tp = Path(task_path)
        candidates.extend(
            [
                tp / "input" / "attribute_dependencies.json",
                tp / "attribute_dependencies.json",
                repo / tp / "input" / "attribute_dependencies.json",
                repo / tp / "attribute_dependencies.json",
            ]
        )

    if instrument_id:
        raw_id = str(instrument_id).strip()
        clean_id = raw_id.removeprefix("survey_").removeprefix("survey-")
        candidates.extend(
            [
                repo / "application" / "tasks" / raw_id / "input" / "attribute_dependencies.json",
                repo / "application" / "tasks" / f"survey_{raw_id}" / "input" / "attribute_dependencies.json",
                repo / "application" / "tasks" / f"survey_{clean_id}" / "input" / "attribute_dependencies.json",
                repo / "application" / "tasks" / f"survey-{clean_id}" / "input" / "attribute_dependencies.json",
                repo / "application" / "tasks" / f"survey_{clean_id.replace('-', '_')}" / "input" / "attribute_dependencies.json",
                repo / "application" / "tasks" / f"survey_{clean_id.replace('_', '-')}" / "input" / "attribute_dependencies.json",
                repo / "tasks" / raw_id / "input" / "attribute_dependencies.json",
                repo / "tasks" / f"survey_{clean_id}" / "input" / "attribute_dependencies.json",
            ]
        )

    for cand in candidates:
        if cand.is_file():
            return cand.resolve()

    return None



def load_task_unique_attributes(
    deps_path_or_task: Union[str, Path],
    instrument_id: Optional[str] = None,
) -> Set[str]:
    """Extract all unique attribute IDs from attribute_dependencies.json."""
    target_path: Optional[Path] = None
    if deps_path_or_task:
        p = Path(deps_path_or_task)
        if p.is_file():
            target_path = p.resolve()
        else:
            target_path = find_task_attribute_dependencies_path(
                task_path=deps_path_or_task, instrument_id=instrument_id
            )

    if not target_path or not target_path.is_file():
        return set()

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    unique_attrs: Set[str] = set()

    # 1. From top-level unique_attributes list
    for item in data.get("unique_attributes", []):
        if isinstance(item, dict) and "id" in item:
            unique_attrs.add(str(item["id"]).strip())
        elif isinstance(item, str):
            unique_attrs.add(item.strip())

    # 2. From per-question dependencies
    for q in data.get("questions", []):
        for dep in q.get("dependencies", []):
            if isinstance(dep, dict):
                attr_id = dep.get("attribute_id") or dep.get("dimension_id")
                if attr_id:
                    unique_attrs.add(str(attr_id).strip())

    return unique_attrs



def prune_persona_dimensions(
    dimensions: Dict[str, Any],
    allowed_attribute_ids: Union[Set[str], List[str]],
    strategy: str = "task_dependencies",
) -> Dict[str, Any]:
    """Filter a persona dimensions dictionary according to the chosen strategy."""
    norm_strategy = str(strategy or "full").strip().lower()
    if norm_strategy == "full":
        return dimensions

    allowed = set(allowed_attribute_ids)
    if norm_strategy == "hybrid":
        allowed = allowed | CORE_DEMOGRAPHIC_ATTRIBUTES

    return {k: v for k, v in dimensions.items() if k in allowed}



def prune_persona_object(
    persona: Any,
    strategy: str = "full",
    task_path: Optional[Union[str, Path]] = None,
    instrument_id: Optional[str] = None,
    deps_path: Optional[Union[str, Path]] = None,
) -> Any:
    """Return a new Persona object with pruned dimensions if strategy is not 'full'."""
    norm_strategy = str(strategy or "full").strip().lower()
    if norm_strategy == "full":
        return persona

    # Determine unique attributes
    allowed_ids: Set[str] = set()
    if deps_path:
        allowed_ids = load_task_unique_attributes(deps_path)
    elif task_path or instrument_id:
        allowed_ids = load_task_unique_attributes(task_path or "", instrument_id=instrument_id)

    if not allowed_ids:
        # If no dependencies file was found, fallback to original persona
        return persona

    new_data = dict(getattr(persona, "data", {}))
    if "dimensions" in new_data and isinstance(new_data["dimensions"], dict):
        new_data["dimensions"] = prune_persona_dimensions(
            new_data["dimensions"],
            allowed_attribute_ids=allowed_ids,
            strategy=norm_strategy,
        )

    from matraix.agents.persona.loader import Persona

    return Persona(
        persona_path=getattr(persona, "persona_path", Path("")),
        schema_version=getattr(persona, "schema_version", "v1"),
        data=new_data,
        persona_id=getattr(persona, "persona_id", None),
        version=getattr(persona, "version", None),
        display_name=getattr(persona, "display_name", None),
        summary=getattr(persona, "summary", None),
        system_prompt=getattr(persona, "system_prompt", None),
    )
