"""LLM-as-a-Judge Evaluator for Persona Attribute Adherence and Causal Impact."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from .llm_client import BaseLLMClient, MockLLMClient, OpenAILLMClient

# =====================================================================
# Prompt Templates for LLM Judge
# =====================================================================

ADHERENCE_JUDGE_SYSTEM_PROMPT = """You are an expert Persona Behavioral & Causal Adherence Judge in an AI Persona Simulation System (MatrAIx Persona).
Your mission is to rigorously evaluate whether an AI Persona's simulated response to a survey question is causally consistent with, contradictory to, or unaffected by the Persona's specific ground-truth attribute values.

For each evaluated attribute, you must classify its relationship with the chosen answer into one of three strict categories:
1. "CONSISTENT": The persona's specific attribute value logically, psychologically, or statistically supports and justifies the chosen answer.
2. "CONTRADICTORY": The persona's specific attribute value should logically lead to an opposing or substantially different response, yet the persona chose this answer anyway.
3. "NEUTRAL": The persona's attribute value is balanced/neutral, or does not create a strong directional bias toward or against this specific answer.

Be objective, analytical, and provide clear causal rationales. Always respond in valid JSON format.
"""

ADHERENCE_JUDGE_USER_PROMPT = """### Survey Question:
Question ID: {question_id}
Prompt: "{question_prompt}"
{options_text}

### Persona Simulated Answer:
Selected Value / Response: {answer_value}
{answer_reasoning_text}

### Evaluated Persona Attributes & Ground-Truth Values:
{attributes_context_text}

### Task:
Evaluate each of the persona attributes listed above against the persona's selected response.
For every attribute:
1. Verify the persona's actual value.
2. Determine the classification: "CONSISTENT" | "CONTRADICTORY" | "NEUTRAL".
3. Assign a numeric score: +1.0 for CONSISTENT, -1.0 for CONTRADICTORY, 0.0 for NEUTRAL.
4. Provide a concise, insightful explanation ('reasoning') justifying your verdict based on the causal mechanism.

### Response format (JSON only):
{{
  "question_id": "{question_id}",
  "evaluated_attributes": [
    {{
      "attribute_id": "id_of_attribute",
      "attribute_label": "Label of attribute",
      "persona_value": "Persona's actual value",
      "classification": "CONSISTENT",
      "score": 1.0,
      "reasoning": "Concise causal justification for this verdict."
    }}
  ],
  "question_summary": "Brief summary of overall persona consistency for this question."
}}
"""


# =====================================================================
# Data Structures for Adherence Results
# =====================================================================

@dataclass
class AttributeAdherenceVerdict:
    """Verdict for a single persona attribute on a single question."""

    attribute_id: str
    attribute_label: str
    persona_value: Any
    classification: str  # "CONSISTENT" | "CONTRADICTORY" | "NEUTRAL" | "MISSING_VALUE"
    score: float  # +1.0, -1.0, 0.0
    reasoning: str = ""
    category: Optional[str] = None
    expected_relevance: str = "high"  # from dependency extraction

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuestionAdherenceResult:
    """Adherence evaluation result for a single survey question."""

    question_id: str
    question_prompt: str
    selected_answer: Any
    answer_reasoning: Optional[str] = None
    verdicts: List[AttributeAdherenceVerdict] = field(default_factory=list)
    question_summary: str = ""

    @property
    def total_evaluated(self) -> int:
        return len(self.verdicts)

    @property
    def consistent_count(self) -> int:
        return sum(1 for v in self.verdicts if v.classification.upper() == "CONSISTENT")

    @property
    def contradictory_count(self) -> int:
        return sum(1 for v in self.verdicts if v.classification.upper() == "CONTRADICTORY")

    @property
    def neutral_count(self) -> int:
        return sum(1 for v in self.verdicts if v.classification.upper() == "NEUTRAL")

    @property
    def adherence_rate(self) -> float:
        """Percentage of decisive attributes that are consistent (excluding neutral)."""
        decisive = self.consistent_count + self.contradictory_count
        if decisive == 0:
            return 1.0 if self.neutral_count > 0 else 0.0
        return self.consistent_count / decisive

    @property
    def average_score(self) -> float:
        if not self.verdicts:
            return 0.0
        return sum(v.score for v in self.verdicts) / len(self.verdicts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_prompt": self.question_prompt,
            "selected_answer": self.selected_answer,
            "answer_reasoning": self.answer_reasoning,
            "total_evaluated": self.total_evaluated,
            "consistent_count": self.consistent_count,
            "contradictory_count": self.contradictory_count,
            "neutral_count": self.neutral_count,
            "adherence_rate": round(self.adherence_rate, 4),
            "average_score": round(self.average_score, 4),
            "question_summary": self.question_summary,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


@dataclass
class SurveyAdherenceResult:
    """Comprehensive adherence evaluation result for an entire survey trial."""

    survey_id: str
    survey_title: str
    persona_id: str
    persona_name: str
    questions: List[QuestionAdherenceResult] = field(default_factory=list)
    evaluated_at: Optional[str] = None

    @property
    def total_attributes_evaluated(self) -> int:
        return sum(q.total_evaluated for q in self.questions)

    @property
    def total_consistent(self) -> int:
        return sum(q.consistent_count for q in self.questions)

    @property
    def total_contradictory(self) -> int:
        return sum(q.contradictory_count for q in self.questions)

    @property
    def total_neutral(self) -> int:
        return sum(q.neutral_count for q in self.questions)

    @property
    def overall_adherence_rate(self) -> float:
        decisive = self.total_consistent + self.total_contradictory
        if decisive == 0:
            return 1.0 if self.total_neutral > 0 else 0.0
        return self.total_consistent / decisive

    @property
    def overall_average_score(self) -> float:
        if not self.questions:
            return 0.0
        total_verdicts = sum(len(q.verdicts) for q in self.questions)
        if total_verdicts == 0:
            return 0.0
        return sum(sum(v.score for v in q.verdicts) for q in self.questions) / total_verdicts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "survey_title": self.survey_title,
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "evaluated_at": self.evaluated_at,
            "summary": {
                "total_questions": len(self.questions),
                "total_attributes_evaluated": self.total_attributes_evaluated,
                "total_consistent": self.total_consistent,
                "total_contradictory": self.total_contradictory,
                "total_neutral": self.total_neutral,
                "overall_adherence_rate": round(self.overall_adherence_rate, 4),
                "overall_average_score": round(self.overall_average_score, 4),
            },
            "questions": [q.to_dict() for q in self.questions],
        }

    def print_summary(self) -> None:
        """Print clean formatted summary to console."""
        print("\n" + "=" * 70)
        print(f"  Persona Adherence Evaluation: {self.persona_name} ({self.persona_id})")
        print(f"  Survey: '{self.survey_title}'")
        print("=" * 70)
        print(f"  Total Questions Evaluated:     {len(self.questions)}")
        print(f"  Total Attribute Evaluations:   {self.total_attributes_evaluated}")
        print(f"  [+] Consistent Attributes:     {self.total_consistent}")
        print(f"  [-] Contradictory Attributes:  {self.total_contradictory}")
        print(f"  [o] Neutral / Unaffected:       {self.total_neutral}")
        print(f"  [*] Overall Adherence Rate:    {self.overall_adherence_rate * 100:.1f}%")
        print(f"  [#] Average Score (-1 to +1):   {self.overall_average_score:+.2f}")
        print("=" * 70)

        for idx, q in enumerate(self.questions, 1):
            print(f"\n[Q{idx}] {q.question_id}: \"{q.question_prompt}\"")
            print(f"  Selected Answer: {q.selected_answer}")
            print(f"  Adherence: {q.consistent_count} Consistent | {q.contradictory_count} Contradictory | {q.neutral_count} Neutral")
            for v in q.verdicts:
                tag = "[+]" if v.classification == "CONSISTENT" else ("[-]" if v.classification == "CONTRADICTORY" else "[o]")
                print(f"    {tag} {v.attribute_label} ({v.attribute_id}): {v.persona_value} -> {v.classification} ({v.score:+.1f})")
                if v.reasoning:
                    print(f"        Why: {v.reasoning}")


# =====================================================================
# Main Evaluator Engine
# =====================================================================

class PersonaAttributeAdherenceEvaluator:
    """Evaluates causal adherence of simulated persona survey answers against profile traits."""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        verbose: bool = True,
    ):
        self.llm_client = llm_client or OpenAILLMClient()
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def evaluate_survey_trial(
        self,
        persona_data: Union[Dict[str, Any], Path, str],
        survey_result_data: Union[Dict[str, Any], Path, str],
        attribute_dependencies_data: Union[Dict[str, Any], Path, str],
    ) -> SurveyAdherenceResult:
        """Run LLM-as-a-Judge adherence evaluation for an entire simulated survey trial."""
        # 1. Load Persona Data
        persona_dict = self._resolve_json_or_yaml(persona_data)
        persona_dimensions = persona_dict.get("dimensions", {}) or {}
        persona_id = str(persona_dict.get("persona_id", "persona_unknown"))
        persona_name = str(persona_dict.get("display_name", persona_dict.get("name", persona_id)))

        # 2. Load Survey Result Data
        survey_result = self._resolve_json_or_yaml(survey_result_data)
        answers_list = survey_result.get("answers", [])
        answers_map: Dict[str, Dict[str, Any]] = {}
        for ans in answers_list:
            if isinstance(ans, dict):
                qid = str(ans.get("questionId") or ans.get("question_id") or ans.get("id", "")).strip()
                if qid:
                    answers_map[qid] = ans

        # 3. Load Attribute Dependencies Data
        deps_data = self._resolve_json_or_yaml(attribute_dependencies_data)
        survey_id = str(deps_data.get("survey_id", "survey_1"))
        survey_title = str(deps_data.get("survey_title", "Survey Task"))
        dep_questions = deps_data.get("questions", [])

        self._log(f"\n=======================================================")
        self._log(f"[Adherence Judge] Evaluating Persona: '{persona_name}' ({persona_id})")
        self._log(f"Survey: '{survey_title}' ({len(dep_questions)} questions)")
        self._log(f"=======================================================")

        question_results: List[QuestionAdherenceResult] = []

        # 4. Evaluate Question by Question
        for q_dep in dep_questions:
            q_id = str(q_dep.get("question_id") or q_dep.get("id", ""))
            q_prompt = q_dep.get("prompt") or q_dep.get("question_text", "")
            q_options = q_dep.get("options", [])
            dependencies = q_dep.get("dependencies", [])

            ans_obj = answers_map.get(q_id, {})
            selected_value = ans_obj.get("value")
            answer_reasoning = ans_obj.get("reasoning") or ans_obj.get("explanation")

            if selected_value is None:
                self._log(f"[Warning] Question '{q_id}' has no simulated answer in survey_result. Skipping.")
                continue

            if not dependencies:
                self._log(f"[Info] Question '{q_id}' has no dependent attributes defined. Skipping.")
                continue

            q_result = self.evaluate_question(
                question_id=q_id,
                question_prompt=q_prompt,
                options=q_options,
                selected_answer=selected_value,
                answer_reasoning=answer_reasoning,
                dependencies=dependencies,
                persona_dimensions=persona_dimensions,
            )
            question_results.append(q_result)

        import datetime
        final_result = SurveyAdherenceResult(
            survey_id=survey_id,
            survey_title=survey_title,
            persona_id=persona_id,
            persona_name=persona_name,
            questions=question_results,
            evaluated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        if self.verbose:
            final_result.print_summary()

        return final_result

    def evaluate_question(
        self,
        question_id: str,
        question_prompt: str,
        options: List[Any],
        selected_answer: Any,
        answer_reasoning: Optional[str],
        dependencies: List[Dict[str, Any]],
        persona_dimensions: Dict[str, Any],
    ) -> QuestionAdherenceResult:
        """Run judge on a single question with its dependent attributes."""
        # Format options
        options_text = ""
        if options:
            options_text = "Options: " + ", ".join(f"[{opt}]" for opt in options)

        # Format reasoning
        answer_reasoning_text = ""
        if answer_reasoning:
            answer_reasoning_text = f"Persona's Stated Reasoning: \"{answer_reasoning}\""

        # Build attribute context items
        attr_context_lines = []
        valid_deps = []
        for dep in dependencies:
            attr_id = dep.get("attribute_id") or dep.get("dimension_id") or dep.get("id", "")
            attr_label = dep.get("attribute_label") or dep.get("dimension_label") or dep.get("label", attr_id)
            expected_reason = dep.get("reason") or dep.get("reasoning", "")
            relevance = dep.get("relevance") or dep.get("relevance_strength", "high")
            
            # Fetch persona's actual ground-truth value
            persona_val = persona_dimensions.get(attr_id)
            if persona_val is None:
                # Value not set in persona profile
                persona_val = "Not specified / Default"

            line = (
                f"- Attribute: '{attr_label}' ({attr_id})\n"
                f"  Persona Ground-Truth Value: \"{persona_val}\"\n"
                f"  Expected Causal Role: {expected_reason} (Relevance: {relevance})"
            )
            attr_context_lines.append(line)
            valid_deps.append({
                "id": attr_id,
                "label": attr_label,
                "persona_val": persona_val,
                "category": dep.get("category"),
                "relevance": relevance,
            })

        attributes_context_text = "\n".join(attr_context_lines)

        user_prompt = ADHERENCE_JUDGE_USER_PROMPT.format(
            question_id=question_id,
            question_prompt=question_prompt,
            options_text=options_text,
            answer_value=str(selected_answer),
            answer_reasoning_text=answer_reasoning_text,
            attributes_context_text=attributes_context_text,
        )

        # Call LLM Judge
        try:
            raw_response = self.llm_client.complete(
                prompt=user_prompt,
                system_prompt=ADHERENCE_JUDGE_SYSTEM_PROMPT,
            )
        except Exception as e:
            self._log(f"[Judge Error] LLM evaluation failed on question '{question_id}': {e}")
            raw_response = {"error": str(e), "evaluated_attributes": []}

        # Parse verdicts
        verdicts: List[AttributeAdherenceVerdict] = []
        eval_list = raw_response.get("evaluated_attributes", [])
        eval_map = {item.get("attribute_id"): item for item in eval_list if isinstance(item, dict)}

        for dep_info in valid_deps:
            attr_id = dep_info["id"]
            matched_eval = eval_map.get(attr_id, {})
            
            classification = (matched_eval.get("classification") or "NEUTRAL").upper()
            if classification not in ["CONSISTENT", "CONTRADICTORY", "NEUTRAL"]:
                classification = "NEUTRAL"

            score = matched_eval.get("score")
            if score is None:
                score = 1.0 if classification == "CONSISTENT" else (-1.0 if classification == "CONTRADICTORY" else 0.0)
            else:
                try:
                    score = float(score)
                except ValueError:
                    score = 0.0

            reasoning = matched_eval.get("reasoning") or matched_eval.get("explanation") or ""

            verdicts.append(
                AttributeAdherenceVerdict(
                    attribute_id=attr_id,
                    attribute_label=dep_info["label"],
                    persona_value=dep_info["persona_val"],
                    classification=classification,
                    score=score,
                    reasoning=reasoning,
                    category=dep_info.get("category"),
                    expected_relevance=dep_info.get("relevance", "high"),
                )
            )

        summary_text = raw_response.get("question_summary", "")

        return QuestionAdherenceResult(
            question_id=question_id,
            question_prompt=question_prompt,
            selected_answer=selected_answer,
            answer_reasoning=answer_reasoning,
            verdicts=verdicts,
            question_summary=summary_text,
        )

    @staticmethod
    def _resolve_json_or_yaml(source: Union[Dict[str, Any], Path, str]) -> Dict[str, Any]:
        """Helper to resolve a dict, JSON file path, or YAML file path into a Python dict."""
        if isinstance(source, dict):
            return source

        path = Path(source).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Source file not found at: {path}")

        text = path.read_text(encoding="utf-8")
        if path.suffix in [".yaml", ".yml"]:
            return yaml.safe_load(text) or {}
        return json.loads(text)

