"""Demo script to test LLM-as-a-Judge Persona Attribute Adherence Evaluation."""

from __future__ import annotations

import json
import os
from pathlib import Path

from application.playground.attribute_dependency import (
    MockLLMClient,
    OpenAILLMClient,
    PersonaAttributeAdherenceEvaluator,
)
from application.playground.attribute_dependency.constants import REPO_ROOT


def main():
    print("================================================================")
    print("  MatrAIx Persona: LLM-as-a-Judge Attribute Adherence Evaluation ")
    print("================================================================")

    # 1. Initialize LLM Judge Client
    has_local = bool(os.getenv("LOCAL_LLM_BASE_URL") or os.getenv("LOCAL_LLM_MODEL") or os.getenv("LOCAL_LLM_AUTH_HEADER"))
    has_openai = bool(os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY", "").startswith("dummy"))
    
    if has_local or has_openai:
        llm = OpenAILLMClient()
        print(f"[Judge Client] Using OpenAILLMClient (Model: {llm.model} | Base URL: {llm.base_url or 'default'})")
    else:
        print("[Judge Client] No LLM endpoint detected, using MockLLMClient.")
        llm = MockLLMClient()

    evaluator = PersonaAttributeAdherenceEvaluator(llm_client=llm, verbose=True)

    # 2. Select Sample Persona & Task Files
    persona_yaml = REPO_ROOT / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml"
    task_dependencies = (
        REPO_ROOT
        / "application"
        / "tasks"
        / "survey_price-sensitivity-hasbro-gaming-candy-land"
        / "input"
        / "attribute_dependencies.json"
    )

    # 3. Create a realistic simulated survey result
    simulated_survey_result = {
        "survey_id": "price_sensitivity_v1",
        "answers": [
            {
                "questionId": "q_price_matters",
                "value": "Strongly Disagree",
                "reasoning": "As a skilled tradesman with a risk-seeking mindset, I focus on the craftsmanship and utility of products rather than worrying primarily about the price tag.",
            },
            {
                "questionId": "q_price_vs_quality",
                "value": "I will pay more for quality.",
                "reasoning": "I value long-lasting quality and durability in my possessions and am willing to invest more upfront.",
            },
        ],
    }

    # 4. Run the Evaluation
    print(f"\n[Evaluating] Persona: {persona_yaml.name} against survey task...")
    result = evaluator.evaluate_survey_trial(
        persona_data=persona_yaml,
        survey_result_data=simulated_survey_result,
        attribute_dependencies_data=task_dependencies,
    )

    # 5. Save output report
    output_path = REPO_ROOT / "application" / "playground" / "attribute_dependency" / "sample_adherence_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"\n[Report Saved] Full JSON verdict saved to:\n  -> {output_path}")


if __name__ == "__main__":
    main()

