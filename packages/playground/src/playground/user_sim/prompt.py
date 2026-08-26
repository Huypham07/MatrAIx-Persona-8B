"""Assemble tool-driven user simulator prompts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from playground.task_content_bundle import TaskContentBundle
from playground.types import Persona

_GUIDELINES_PATH = Path(__file__).resolve().parent / "sim_guidelines.md"


def _ensure_persona_agents_package() -> None:
    """Expose the split source package when Playground runs directly from source."""
    try:
        import matraix.agents.persona.loader  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name != "matraix.agents":
            raise
        import matraix

        agents_namespace = (
            Path(__file__).resolve().parents[5] / "environment" / "agents" / "matraix"
        )
        if not agents_namespace.is_dir():
            raise
        matraix.__path__.append(str(agents_namespace))


def load_sim_guidelines() -> str:
    return _GUIDELINES_PATH.read_text(encoding="utf-8").strip()


def current_date_block(*, now: datetime | None = None) -> str:
    """Tell the persona what today/now is (host clock)."""
    moment = now or datetime.now().astimezone()
    return "Today is {weekday}, {month} {day}, {year}, {time}.".format(
        weekday=moment.strftime("%A"),
        month=moment.strftime("%B"),
        day=moment.day,
        year=moment.year,
        time=moment.strftime("%H:%M %Z").strip(),
    )


def _persona_context(persona: Persona) -> str:
    if persona.context:
        return persona.context
    parts = [
        "Name: {}".format(persona.name),
        "Who you are: {}".format(persona.summary or "(a typical user)"),
        "What you want (preferences): {}".format(", ".join(persona.preferences) or "(open)"),
        "What you dislike: {}".format(", ".join(persona.dislikes) or "(none stated)"),
        "Your constraints: {}".format(", ".join(persona.constraints) or "(flexible)"),
        "Your goal: {}".format(persona.goal or "(find something suitable)"),
        "How you talk: {}".format(persona.communication_style or "natural and conversational"),
    ]
    return "\n".join(parts)


def render_persona_block(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_path: Optional[str] = None,
    task_dir: Optional[Path | str] = None,
    include_fields: Optional[list[str] | set[str]] = None,
    exclude_fields: Optional[list[str] | set[str]] = None,
) -> str:
    canonical_path = persona_yaml_path or persona.persona_path
    resolved_task_dir = task_dir or (Path(task_path) if task_path else None)
    if canonical_path:
        _ensure_persona_agents_package()
        from matraix.agents.persona.loader import load_persona
        from matraix.agents.persona.templating import (
            PERSONA_SYSTEM_TEMPLATE,
            render_persona_template,
            resolve_persona_template,
        )

        loaded = load_persona(canonical_path)
        template = resolve_persona_template(loaded, None, PERSONA_SYSTEM_TEMPLATE)
        return render_persona_template(
            template,
            loaded,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
            task_dir=resolved_task_dir,
        ).strip()
    if persona.dimensions:
        raise ValueError("dimension-backed persona requires a canonical persona path")
    return _persona_context(persona)


def persona_primary_language(persona: Persona) -> str:
    """Return the canonical language for persona-authored natural language."""
    value = str((persona.dimensions or {}).get("primary_language") or "").strip()
    return value or "English"


def persona_language_contract(persona: Persona) -> str:
    """High-priority output-language rules shared by every persona LLM path."""
    language = persona_primary_language(persona)
    return (
        "## Required response language\n"
        f"Respond in {language} for every persona-authored natural-language message, "
        "free-text answer, rationale, and feedback explanation. The task may be written "
        "in English; that does not permit switching the persona's response language. "
        "Keep JSON keys, enum values, option IDs, question IDs, URLs, product names, "
        "currencies, numeric values, and copied application text exactly as provided. "
        "Do not translate the canonical persona profile or machine-readable identifiers."
    )


def _section(title: str, body: str) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    return "## {}\n{}".format(title, text)


def assemble_system_prompt(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_bundle: Optional[TaskContentBundle] = None,
    task_path: Optional[str] = None,
    task_dir: Optional[Path | str] = None,
    include_fields: Optional[list[str] | set[str]] = None,
    exclude_fields: Optional[list[str] | set[str]] = None,
) -> str:
    task_bundle = task_bundle or TaskContentBundle()
    resolved_task_dir = task_dir or task_path
    blocks = [
        render_persona_block(
            persona,
            persona_yaml_path=persona_yaml_path,
            task_dir=resolved_task_dir,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        ),
        current_date_block(),
        load_sim_guidelines(),
        _section("Task instruction", task_bundle.instruction_markdown),
        _section("Task context", task_bundle.context_markdown),
        persona_language_contract(persona),
    ]
    return "\n\n".join(block for block in blocks if block.strip())


def assemble_report_system_prompt(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_bundle: Optional[TaskContentBundle] = None,
    task_path: Optional[str] = None,
    task_dir: Optional[Path | str] = None,
    include_fields: Optional[list[str] | set[str]] = None,
    exclude_fields: Optional[list[str] | set[str]] = None,
) -> str:
    task_bundle = task_bundle or TaskContentBundle()
    resolved_task_dir = task_dir or task_path
    blocks = [
        render_persona_block(
            persona,
            persona_yaml_path=persona_yaml_path,
            task_dir=resolved_task_dir,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        ),
        current_date_block(),
        _section("Task instruction", task_bundle.instruction_markdown),
        _section("Task context", task_bundle.context_markdown),
        persona_language_contract(persona),
    ]
    return "\n\n".join(block for block in blocks if block.strip())


def prompt_bundle(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_bundle: Optional[TaskContentBundle] = None,
    task_prompt: str = "",
    task_path: Optional[str] = None,
    task_dir: Optional[Path | str] = None,
    include_fields: Optional[list[str] | set[str]] = None,
    exclude_fields: Optional[list[str] | set[str]] = None,
) -> dict[str, str]:
    task_bundle = task_bundle or TaskContentBundle()
    resolved_task_dir = task_dir or task_path
    persona_block = render_persona_block(
        persona,
        persona_yaml_path=persona_yaml_path,
        task_dir=resolved_task_dir,
        include_fields=include_fields,
        exclude_fields=exclude_fields,
    )
    system = assemble_system_prompt(
        persona,
        persona_yaml_path=persona_yaml_path,
        task_bundle=task_bundle,
        task_dir=resolved_task_dir,
        include_fields=include_fields,
        exclude_fields=exclude_fields,
    )

    task_parts: list[str] = []
    instruction_block = _section("Task instruction", task_bundle.instruction_markdown)
    context_block = _section("Task context", task_bundle.context_markdown)
    if instruction_block:
        task_parts.append(instruction_block)
    if context_block:
        task_parts.append(context_block)
    kickoff = (task_prompt or "").strip()
    if kickoff:
        task_parts.append("## Application kickoff\n{}".format(kickoff))

    return {
        "personaPrompt": persona_block.strip(),
        "harborPrompt": system,
        "taskPrompt": "\n\n".join(task_parts).strip(),
    }
