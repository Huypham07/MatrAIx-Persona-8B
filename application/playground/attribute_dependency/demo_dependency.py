"""Demo script showing Hierarchical Tree Pruning for Survey Question Attribute Dependency."""

from __future__ import annotations

import os
from application.playground.attribute_dependency import (
    HierarchicalAttributePruner,
    MockLLMClient,
    OpenAILLMClient,
    load_or_build_taxonomy_tree,
)


def main():
    print("================================================================")
    print("  MatrAIx Persona: Hierarchical Attribute Dependency Extraction ")
    print("================================================================")

    # 1. Check if LOCAL_LLM_* or OPENAI_API_KEY is configured, otherwise use MockLLMClient for demonstration
    has_local = bool(os.getenv("LOCAL_LLM_BASE_URL") or os.getenv("LOCAL_LLM_MODEL") or os.getenv("LOCAL_LLM_AUTH_HEADER"))
    has_openai = bool(os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY", "").startswith("dummy"))
    if has_local or has_openai:
        llm = OpenAILLMClient()
        print(f"[LLM Client] Using OpenAILLMClient (Model: {llm.model} | Base URL: {llm.base_url or 'default'})")
    else:
        print("[LLM Client] OPENAI_API_KEY not detected, using MockLLMClient for simulation.")
        llm = MockLLMClient()

    # 2. Load the cached 4-layer taxonomy tree
    tree = load_or_build_taxonomy_tree()
    pruner = HierarchicalAttributePruner(tree=tree, llm_client=llm, verbose=True)

    # 3. Define sample survey questions
    sample_survey = {
        "survey_id": "survey_dev_ai_adoption_2026",
        "survey_title": "Developer AI Coding Assistant Adoption & Trust Survey",
        "questions": [
            {
                "id": "q1",
                "prompt": "How frequently do you rely on AI coding assistants (e.g. GitHub Copilot, Cursor) in your daily software engineering workflow?",
                "options": ["Never", "Rarely", "Weekly", "Daily", "Constantly throughout the day"],
            },
            {
                "id": "q2",
                "prompt": "How strongly do you trust AI-generated code for security-critical backend systems without extensive manual review?",
                "options": ["Strongly distrust", "Somewhat distrust", "Neutral", "Somewhat trust", "Completely trust"],
            },
        ],
    }

    # 4. Run the top-down hierarchical pruning
    survey_result = pruner.extract_for_survey(
        questions=sample_survey["questions"],
        survey_id=sample_survey["survey_id"],
        survey_title=sample_survey["survey_title"],
    )

    # 5. Print summary results for each question
    for q_res in survey_result.questions:
        q_res.print_summary()

    # 6. Print aggregated summary for the entire survey
    print("================================================================")
    print(f"Aggregated Results for Survey: '{survey_result.survey_title}'")
    print(f"Total Unique Persona Dimensions Required: {len(survey_result.all_unique_dimensions)}")
    for dim_id, dep in survey_result.all_unique_dimensions.items():
        print(f" - {dep.dimension_label} ({dim_id}) -> {dep.path_label}")
    print("================================================================")


if __name__ == "__main__":
    main()
