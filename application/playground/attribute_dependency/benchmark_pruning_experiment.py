"""Benchmark experiment comparing Full vs Task Dependencies (Pruned) Persona strategies.

Evaluates:
- Prompt character and token length
- Simulation response time
- Attribute Adherence Score and Contradictions (evaluated by PersonaAttributeAdherenceEvaluator)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add repo paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "playground" / "src"))
sys.path.insert(0, str(REPO_ROOT / "environment" / "runtime"))
sys.path.insert(0, str(REPO_ROOT / "environment" / "agents"))
sys.path.insert(0, str(REPO_ROOT / "application"))
sys.path.insert(0, str(REPO_ROOT / "application" / "playground"))

from application.playground.attribute_dependency.adherence_evaluator import (
    PersonaAttributeAdherenceEvaluator,
    SurveyAdherenceResult,
)
from application.playground.attribute_dependency.llm_client import OpenAILLMClient
from application.playground.attribute_dependency.persona_filter import (
    load_task_unique_attributes,
    prune_persona_object,
)
from matraix.agents.persona.loader import load_persona
from matraix.agents.persona.json_survey import (
    _eval_persona,
    _load_survey_content,
    _survey_result_payload,
)
from playground.inprocess.survey_eval import (
    InprocessSurveyEvalRunner,
    SurveyEvalConfig,
)


def run_single_trial(
    persona_yaml_path: str,
    task_path: str,
    strategy: str,
    model_name: str = "local/qwen3-14b",
    llm_client: Any | None = None,
) -> Dict[str, Any]:
    print("=" * 60)
    print(f"Running Trial: Persona={Path(persona_yaml_path).stem} | Strategy={strategy}")
    print("=" * 60)

    raw_persona = load_persona(persona_yaml_path)
    instrument, content = _load_survey_content(task_path=task_path, instrument_path=None)
    eval_persona = _eval_persona(raw_persona)

    survey_config = SurveyEvalConfig(persona_model=model_name)
    runner = InprocessSurveyEvalRunner()

    events: List[Dict[str, Any]] = []

    def on_event(ev: Dict[str, Any]) -> None:
        events.append(ev)

    start_time = time.time()
    result = runner(
        eval_persona,
        instrument,
        config=survey_config,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        on_event=on_event,
        persona_yaml_path=persona_yaml_path,
        persona_attribute_strategy=strategy,
        task_path=task_path,
    )
    elapsed = time.time() - start_time
    payload = _survey_result_payload(result)

    # Extract prompt used
    prompts = next((e.get("prompts") for e in events if e.get("type") == "prompts"), {})
    persona_prompt = prompts.get("personaPrompt", "")

    # Run Adherence Evaluator
    evaluator = PersonaAttributeAdherenceEvaluator(llm_client=llm_client)
    dependencies_path = str(REPO_ROOT / task_path / "input" / "attribute_dependencies.json")
    adherence_result: SurveyAdherenceResult = evaluator.evaluate_survey_trial(
        persona_data=persona_yaml_path,
        survey_result_data=payload,
        attribute_dependencies_data=dependencies_path,
    )

    verdict_dict = adherence_result.to_dict()
    summary = verdict_dict.get("summary", {})

    print(f"Completed in {elapsed:.2f}s")
    print(f"Prompt Length: {len(persona_prompt)} chars")
    print(f"Evaluated Questions: {summary.get('total_questions_evaluated', len(verdict_dict.get('questions', [])))}")
    print(f"Adherence Rate: {summary.get('overall_adherence_rate', 0):.1%}")
    print(f"Contradictions: {summary.get('total_contradictory', 0)}")
    print(f"Consistent Attributes: {summary.get('total_consistent', 0)}")

    return {
        "persona_id": Path(persona_yaml_path).stem,
        "persona_name": getattr(raw_persona, "display_name", None) or getattr(raw_persona, "name", None) or str(getattr(raw_persona, "persona_id", "Unknown")),
        "strategy": strategy,
        "elapsed_seconds": round(elapsed, 2),
        "prompt_chars": len(persona_prompt),
        "survey_answers": payload.get("answers", []),
        "adherence_summary": summary,
        "adherence_details": verdict_dict.get("questions", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Persona Pruning A/B Experiment")
    parser.add_argument(
        "--task",
        default="application/tasks/survey_price-sensitivity-hasbro-gaming-candy-land",
        help="Task path relative to repo root",
    )
    parser.add_argument(
        "--personas",
        nargs="+",
        default=[
            "persona/datasets/matraix-persona-dev-sample/persona_0001.yaml",
            "persona/datasets/matraix-persona-dev-sample/persona_0002.yaml",
        ],
        help="List of persona YAML paths relative to repo root",
    )
    parser.add_argument(
        "--model",
        default="local/qwen3-14b",
        help="Persona and Judge model",
    )
    parser.add_argument(
        "--output",
        default="benchmark_pruning_results.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    llm_client = OpenAILLMClient()

    results: List[Dict[str, Any]] = []

    for persona_rel_path in args.personas:
        full_persona_path = str(REPO_ROOT / persona_rel_path)
        if not Path(full_persona_path).exists():
            print(f"Persona file not found: {full_persona_path}")
            continue

        # 1. Run FULL strategy
        res_full = run_single_trial(
            persona_yaml_path=full_persona_path,
            task_path=args.task,
            strategy="full",
            model_name=args.model,
            llm_client=llm_client,
        )
        results.append(res_full)

        # 2. Run TASK_DEPENDENCIES strategy (pruned)
        res_pruned = run_single_trial(
            persona_yaml_path=full_persona_path,
            task_path=args.task,
            strategy="task_dependencies",
            model_name=args.model,
            llm_client=llm_client,
        )
        results.append(res_pruned)

    # Save results
    output_path = REPO_ROOT / args.output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("                      A/B BENCHMARK EXPERIMENT SUMMARY")
    print("=" * 80)
    print(
        f"{'Persona':<15} | {'Strategy':<18} | {'Prompt Chars':<12} | {'Time (s)':<8} | {'Adherence %':<12} | {'Contradictions':<14}"
    )
    print("-" * 80)
    for r in results:
        p_name = str(r.get("persona_name", ""))[:14]
        strat = str(r.get("strategy", ""))
        p_chars = r.get("prompt_chars", 0)
        elap = r.get("elapsed_seconds", 0)
        adh_val = r.get("adherence_summary", {}).get("overall_adherence_rate", 0)
        adh_str = f"{adh_val:.1%}" if isinstance(adh_val, (int, float)) else "N/A"
        contra = r.get("adherence_summary", {}).get("total_contradictory", 0)
        print(f"{p_name:<15} | {strat:<18} | {p_chars:<12} | {elap:<8} | {adh_str:<12} | {contra:<14}")
    print("=" * 80)
    print(f"Full results saved to: {output_path}")


if __name__ == "__main__":
    main()