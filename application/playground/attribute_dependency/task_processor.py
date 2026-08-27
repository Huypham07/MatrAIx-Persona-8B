"""Process survey tasks directly by task name/path and write attribute dependencies to input/."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from .constants import REPO_ROOT
from .dependency_extractor import (
    AttributeDependency,
    HierarchicalAttributePruner,
    QuestionDependencyResult,
    SurveyDependencyResult,
)
from .llm_client import BaseLLMClient, OpenAILLMClient
from .load_tree import PersonaTaxonomyTree, load_or_build_taxonomy_tree


def resolve_task_dir(task_identifier: Union[str, Path]) -> Path:
    """Resolve task directory from a full path, relative path, or task name."""
    raw_path = Path(task_identifier)

    # 1. Direct path exists
    if raw_path.exists() and raw_path.is_dir():
        return raw_path.resolve()

    # 2. Check relative to current working directory
    cwd_task = (Path.cwd() / raw_path).resolve()
    if cwd_task.exists() and cwd_task.is_dir():
        return cwd_task

    # 3. Check in application/tasks/
    app_task = (REPO_ROOT / "application" / "tasks" / raw_path.name).resolve()
    if app_task.exists() and app_task.is_dir():
        return app_task

    # 4. Check in tasks/
    root_task = (REPO_ROOT / "tasks" / raw_path.name).resolve()
    if root_task.exists() and root_task.is_dir():
        return root_task

    raise FileNotFoundError(
        f"Could not find survey task directory for: '{task_identifier}'.\n"
        f"Looked in:\n"
        f" - {raw_path}\n"
        f" - {cwd_task}\n"
        f" - {app_task}\n"
        f" - {root_task}"
    )


def load_task_survey_inputs(task_dir: Path) -> Dict[str, Any]:
    """Find and parse questionnaire and context files inside task input/ directory."""
    input_dir = task_dir / "input"
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found in task: {input_dir}")

    # 1. Locate questionnaire file (.yaml or .json)
    questionnaire_file = None
    for candidate in [
        input_dir / "questionnaire.yaml",
        input_dir / "questionnaire.yml",
        input_dir / "questionnaire.json",
    ]:
        if candidate.exists():
            questionnaire_file = candidate
            break

    if not questionnaire_file:
        raise FileNotFoundError(
            f"No questionnaire.yaml or questionnaire.json found in {input_dir}"
        )

    # Parse questionnaire
    with open(questionnaire_file, "r", encoding="utf-8") as f:
        if questionnaire_file.suffix in [".yaml", ".yml"]:
            questionnaire_data = yaml.safe_load(f)
        else:
            questionnaire_data = json.load(f)

    # 2. Locate context file if present (.md or .txt)
    context_text = ""
    for candidate in [input_dir / "context.md", input_dir / "context.txt"]:
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                context_text = f.read().strip()
            break

    return {
        "task_dir": task_dir,
        "input_dir": input_dir,
        "questionnaire_file": questionnaire_file,
        "questionnaire_data": questionnaire_data,
        "context_text": context_text,
    }


def process_task_attribute_dependencies(
    task_identifier: Union[str, Path],
    output_filename: str = "attribute_dependencies.json",
    llm_client: Optional[BaseLLMClient] = None,
    tree: Optional[PersonaTaxonomyTree] = None,
    verbose: bool = True,
) -> Path:
    """Read task questions from input/, extract attribute dependencies via LLM tree pruning, and save into input/.

    Args:
        task_identifier: Path or name of the task (e.g., 'survey_price-sensitivity-hasbro-gaming-candy-land').
        output_filename: Output JSON filename to write into task's input/ folder.
        llm_client: LLM client (OpenAILLMClient or MockLLMClient).
        tree: Pre-built PersonaTaxonomyTree (loaded from cache if None).
        verbose: Whether to print progress logs.

    Returns:
        Path to the saved attribute dependencies file.
    """
    # 1. Resolve task directory & read inputs
    task_dir = resolve_task_dir(task_identifier)
    task_info = load_task_survey_inputs(task_dir)

    q_data = task_info["questionnaire_data"]
    context_text = task_info["context_text"]
    input_dir = task_info["input_dir"]

    survey_id = q_data.get("id", task_dir.name)
    survey_title = q_data.get("title", task_dir.name)
    questions_raw = q_data.get("questions", [])

    if verbose:
        print(f"\n=======================================================")
        print(f"Task: {task_dir.name}")
        print(f"Directory: {task_dir}")
        print(f"Survey Title: {survey_title}")
        print(f"Total Questions: {len(questions_raw)}")
        if context_text:
            print(f"Context Loaded: Yes ({len(context_text)} chars)")
        print(f"=======================================================")

    # 2. Setup LLM client
    if llm_client is None:
        has_local = bool(os.getenv("LOCAL_LLM_BASE_URL") or os.getenv("LOCAL_LLM_MODEL") or os.getenv("LOCAL_LLM_AUTH_HEADER"))
        has_openai = bool(os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY", "").startswith("dummy"))
        if has_local or has_openai:
            llm_client = OpenAILLMClient()
            if verbose:
                print(f"[LLM Client] Using OpenAILLMClient (Model: {llm_client.model} | Base URL: {llm_client.base_url or 'default'})")
        else:
            if verbose:
                raise RuntimeError("[Warning][process_task_attribute_dependencies] No LLM configuration detected. Using MockLLMClient for simulation.")

    # 3. Setup Pruner
    if tree is None:
        tree = load_or_build_taxonomy_tree()

    pruner = HierarchicalAttributePruner(tree=tree, llm_client=llm_client, verbose=verbose)

    # 4. Extract dependencies for each question
    extracted_questions = []
    unique_attrs_map: Dict[str, AttributeDependency] = {}

    for i, q in enumerate(questions_raw, 1):
        q_id = q.get("id", f"q{i}")
        prompt_text = q.get("prompt") or q.get("question") or ""
        construct = q.get("construct")
        q_type = q.get("type", "likert")

        # Format options
        options = []
        raw_options = q.get("options", [])
        if raw_options:
            if isinstance(raw_options[0], dict):
                options = [opt.get("label") or opt.get("id", "") for opt in raw_options]
            else:
                options = [str(opt) for opt in raw_options]

        # Run hierarchical pruning
        q_result = pruner.extract_for_question(
            question_text=prompt_text,
            question_id=q_id,
            options=options,
            context_text=context_text,
        )

        formatted_deps = []
        for dep in q_result.dependencies:
            unique_attrs_map[dep.dimension_id] = dep
            formatted_deps.append({
                "attribute_id": dep.dimension_id,
                "attribute_label": dep.dimension_label,
                "path": dep.path_label,
                "path_id": dep.path,
                "category": dep.category,
                "relevance": dep.relevance_strength,
                "reason": dep.reasoning,
                "values": dep.values,
            })

        extracted_questions.append({
            "question_id": q_id,
            "prompt": prompt_text,
            "construct": construct,
            "type": q_type,
            "options": options,
            "total_dependencies": len(formatted_deps),
            "dependencies": formatted_deps,
        })

    # 5. Build final output payload
    output_payload = {
        "schemaVersion": "1.0",
        "task_name": task_dir.name,
        "task_path": str(task_dir),
        "survey_id": survey_id,
        "survey_title": survey_title,
        "survey_description": q_data.get("description", ""),
        "generated_at": datetime.datetime.now().isoformat(),
        "total_questions": len(extracted_questions),
        "total_unique_attributes": len(unique_attrs_map),
        "unique_attributes": [
            {
                "id": dep.dimension_id,
                "label": dep.dimension_label,
                "path": dep.path_label,
                "category": dep.category,
                "values_count": len(dep.values),
            }
            for dep in unique_attrs_map.values()
        ],
        "questions": extracted_questions,
    }

    # 6. Save directly into input/ folder
    output_path = input_dir / output_filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    # 7. Generate interactive visualization HTML
    try:
        from .visualize_dependency import generate_visualizer_file
        html_out = input_dir / "attribute_dependencies_visualizer.html"
        generate_visualizer_file(
            dependencies_path=output_path,
            output_path=html_out,
            open_browser=False,
        )
    except Exception as e:
        if verbose:
            print(f"[Warning] Could not generate visualizer HTML: {e}")

    if verbose:
        print(f"\n[Success] Attribute dependencies saved to:\n  -> {output_path}")
        print(f"Summary: {len(extracted_questions)} questions, {len(unique_attrs_map)} unique influencing attributes.")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Extract attribute dependencies for a survey task and save to input/."
    )
    parser.add_argument(
        "task",
        nargs="?",
        default="survey_price-sensitivity-hasbro-gaming-candy-land",
        help="Task name or path (e.g. 'survey_price-sensitivity-hasbro-gaming-candy-land').",
    )
    parser.add_argument(
        "--output-file",
        default="attribute_dependencies.json",
        help="Output filename to create inside task's input/ directory (default: attribute_dependencies.json).",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LOCAL_LLM_MODEL", "Qwen3-14B"),
        help="LLM model name (default: Qwen3-14B).",
    )

    args = parser.parse_args()

    has_local = bool(os.getenv("LOCAL_LLM_BASE_URL") or os.getenv("LOCAL_LLM_MODEL") or os.getenv("LOCAL_LLM_AUTH_HEADER"))
    has_openai = bool(os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY", "").startswith("dummy"))
    if has_local or has_openai:
        model_arg = args.model if args.model != "gpt-4o-mini" else None
        client = OpenAILLMClient(model=model_arg)
    else:
        raise RuntimeError("[Info] No API key or LOCAL_LLM_* configured. Using MockLLMClient.")

    process_task_attribute_dependencies(
        task_identifier=args.task,
        output_filename=args.output_file,
        llm_client=client,
        verbose=True,
    )


if __name__ == "__main__":
    main()
