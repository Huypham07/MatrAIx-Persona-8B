"""Hierarchical Attribute Dependency Extractor using LLM and Tree Pruning."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from .constants import TAXONOMY_TREE_CACHE
from .llm_client import BaseLLMClient, OpenAILLMClient
from .load_tree import PersonaTaxonomyTree, TreeNode, load_or_build_taxonomy_tree
from .prompts import (
    LAYER_1_FILTER_PROMPT,
    LAYER_2_FILTER_PROMPT,
    LAYER_3_FILTER_PROMPT,
    LAYER_4_DIMENSIONS_PROMPT,
    SYSTEM_PROMPT,
)


@dataclass
class AttributeDependency:
    """A specific persona attribute (leaf dimension) that influences a survey question."""

    dimension_id: str
    dimension_label: str
    path: str
    path_label: str
    category: Optional[str] = None
    description: Optional[str] = None
    values: List[str] = field(default_factory=list)
    reasoning: str = ""
    relevance_strength: str = "high"  # "high" | "medium" | "low"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuestionDependencyResult:
    """Dependency analysis result for a single survey question."""

    question_id: str
    question_text: str
    options: List[str] = field(default_factory=list)
    dependencies: List[AttributeDependency] = field(default_factory=list)
    traversal_log: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def total_attributes(self) -> int:
        return len(self.dependencies)

    @property
    def high_relevance_attributes(self) -> List[AttributeDependency]:
        return [d for d in self.dependencies if d.relevance_strength.lower() == "high"]

    @property
    def medium_relevance_attributes(self) -> List[AttributeDependency]:
        return [d for d in self.dependencies if d.relevance_strength.lower() == "medium"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "options": self.options,
            "total_attributes": self.total_attributes,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "traversal_log": self.traversal_log,
        }

    def print_summary(self) -> None:
        """Print clean human-readable summary of identified dependencies."""
        print(f"\n=======================================================")
        print(f"Question [{self.question_id}]: \"{self.question_text}\"")
        if self.options:
            print(f"Options: {', '.join(self.options)}")
        print(f"Total Identified Influencing Attributes: {self.total_attributes}")
        print(f"  - High Relevance:   {len(self.high_relevance_attributes)}")
        print(f"  - Medium Relevance: {len(self.medium_relevance_attributes)}")
        print(f"-------------------------------------------------------")
        for i, dep in enumerate(self.dependencies, 1):
            strength = f"[{dep.relevance_strength.upper()}]"
            print(f"{i:2d}. {strength} {dep.dimension_label} ({dep.dimension_id})")
            print(f"    Path:      {dep.path_label}")
            print(f"    Reasoning: {dep.reasoning}")
            if dep.values:
                val_preview = ", ".join(dep.values[:5])
                if len(dep.values) > 5:
                    val_preview += f" ... (+{len(dep.values)-5} more)"
                print(f"    Values:    [{val_preview}]")
        print(f"=======================================================\n")


@dataclass
class SurveyDependencyResult:
    """Aggregated dependency analysis result for an entire survey."""

    survey_id: str
    survey_title: str
    questions: List[QuestionDependencyResult] = field(default_factory=list)

    @property
    def all_unique_dimensions(self) -> Dict[str, AttributeDependency]:
        """Dictionary of unique dimensions across all questions."""
        unique: Dict[str, AttributeDependency] = {}
        for q in self.questions:
            for dep in q.dependencies:
                if dep.dimension_id not in unique:
                    unique[dep.dimension_id] = dep
        return unique

    def to_dict(self) -> Dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "survey_title": self.survey_title,
            "total_questions": len(self.questions),
            "total_unique_attributes": len(self.all_unique_dimensions),
            "questions": [q.to_dict() for q in self.questions],
        }

    def save_to_json(self, output_path: Union[str, Path], indent: int = 2) -> Path:
        """Save results to a JSON report file."""
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)
        return target_path


class HierarchicalAttributePruner:
    """Hierarchical top-down Tree Pruner using LLM to extract attribute dependencies."""

    def __init__(
        self,
        tree: Optional[PersonaTaxonomyTree] = None,
        llm_client: Optional[BaseLLMClient] = None,
        verbose: bool = True,
    ):
        self.tree = tree or load_or_build_taxonomy_tree()
        self.llm_client = llm_client or OpenAILLMClient()
        self.verbose = verbose

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    @staticmethod
    def _format_options(options: Optional[List[str]]) -> str:
        if not options:
            return ""
        return "Options:\n" + "\n".join(f" - {opt}" for opt in options)

    def extract_for_question(
        self,
        question_text: str,
        question_id: str = "q1",
        options: Optional[List[str]] = None,
        context_text: Optional[str] = None,
    ) -> QuestionDependencyResult:
        """Extract all persona attributes influencing a single survey question via top-down tree search."""
        self._log(f"\n[Tree Pruner] Starting analysis for Question [{question_id}]: \"{question_text}\"")

        traversal_log: List[Dict[str, Any]] = []
        options_text = self._format_options(options)
        ctx_text = f"### Survey & Context Details:\n{context_text.strip()}\n" if context_text else ""

        # ---------------------------------------------------------------------
        # STEP 1: Filter Layer 1 Groups (Top-level 5 groups)
        # ---------------------------------------------------------------------
        l1_nodes = self.tree.root.children
        l1_candidates_str = "\n".join(
            f" - ID: '{n.id}', Label: '{n.label}' ({n.expected_count} dimensions)"
            for n in l1_nodes
        )

        p1 = LAYER_1_FILTER_PROMPT.format(
            question_text=question_text,
            options_text=options_text,
            context_text=ctx_text,
            candidates_text=l1_candidates_str,
        )
        resp1 = self.llm_client.complete(p1, system_prompt=SYSTEM_PROMPT)
        selected_l1_ids = resp1.get("selected_ids", [])
        l1_reasoning = resp1.get("reasoning", "")

        active_l1_nodes = [n for n in l1_nodes if n.id in selected_l1_ids]
        if not active_l1_nodes:
            # Fallback to all if LLM returned empty
            active_l1_nodes = l1_nodes

        self._log(f"  [Layer 1 Filter] Selected {len(active_l1_nodes)}/{len(l1_nodes)} groups: "
                  f"{[n.id for n in active_l1_nodes]}")

        traversal_log.append({
            "level": 1,
            "evaluated_count": len(l1_nodes),
            "selected_ids": [n.id for n in active_l1_nodes],
            "reasoning": l1_reasoning,
        })

        # ---------------------------------------------------------------------
        # STEP 2: Filter Layer 2 Subgroups under active Layer 1 groups
        # ---------------------------------------------------------------------
        active_l2_nodes: List[TreeNode] = []
        for l1_node in active_l1_nodes:
            l2_children = l1_node.children
            if not l2_children:
                continue

            l2_candidates_str = "\n".join(
                f" - ID: '{n.id}', Label: '{n.label}' ({n.expected_count} dimensions)"
                for n in l2_children
            )
            p2 = LAYER_2_FILTER_PROMPT.format(
                question_text=question_text,
                options_text=options_text,
                context_text=ctx_text,
                parent_label=l1_node.label,
                parent_id=l1_node.id,
                candidates_text=l2_candidates_str,
            )
            resp2 = self.llm_client.complete(p2, system_prompt=SYSTEM_PROMPT)
            selected_l2_ids = resp2.get("selected_ids", [])
            l2_reasoning = resp2.get("reasoning", "")

            retained = [n for n in l2_children if n.id in selected_l2_ids]
            active_l2_nodes.extend(retained)

            traversal_log.append({
                "level": 2,
                "parent_id": l1_node.id,
                "evaluated_count": len(l2_children),
                "selected_ids": [n.id for n in retained],
                "reasoning": l2_reasoning,
            })

        self._log(f"  [Layer 2 Filter] Selected {len(active_l2_nodes)} subgroups: "
                  f"{[n.id for n in active_l2_nodes]}")

        # ---------------------------------------------------------------------
        # STEP 3: Filter Layer 3 Categories under active Layer 2 subgroups
        # ---------------------------------------------------------------------
        active_l3_nodes: List[TreeNode] = []
        for l2_node in active_l2_nodes:
            l3_children = l2_node.children
            if not l3_children:
                continue

            l3_candidates_str = "\n".join(
                f" - ID: '{n.id}', Label: '{n.label}' ({len(n.children)} dimensions)"
                for n in l3_children
            )
            p3 = LAYER_3_FILTER_PROMPT.format(
                question_text=question_text,
                options_text=options_text,
                context_text=ctx_text,
                parent_label=l2_node.label,
                parent_id=l2_node.id,
                candidates_text=l3_candidates_str,
            )
            resp3 = self.llm_client.complete(p3, system_prompt=SYSTEM_PROMPT)
            selected_l3_ids = resp3.get("selected_ids", [])
            l3_reasoning = resp3.get("reasoning", "")

            retained = [n for n in l3_children if n.id in selected_l3_ids]
            active_l3_nodes.extend(retained)

            traversal_log.append({
                "level": 3,
                "parent_id": l2_node.id,
                "evaluated_count": len(l3_children),
                "selected_ids": [n.id for n in retained],
                "reasoning": l3_reasoning,
            })

        self._log(f"  [Layer 3 Filter] Selected {len(active_l3_nodes)} categories: "
                  f"{[n.id for n in active_l3_nodes]}")

        # ---------------------------------------------------------------------
        # STEP 4: Select Leaf Dimensions under active Layer 3 categories
        # ---------------------------------------------------------------------
        dependencies: List[AttributeDependency] = []
        seen_dim_ids: Set[str] = set()

        for l3_node in active_l3_nodes:
            dim_children = [c for c in l3_node.children if c.is_dimension]
            if not dim_children:
                continue

            # Build detailed candidate descriptions
            dim_descriptions = []
            dim_map = {d.id: d for d in dim_children}
            for d in dim_children:
                val_str = f", values={d.values[:6]}" if d.values else ""
                desc = f" - ID: '{d.id}', Label: '{d.label}'{val_str}"
                if d.description:
                    desc += f" (Description: {d.description})"
                dim_descriptions.append(desc)

            candidates_text = "\n".join(dim_descriptions)
            p4 = LAYER_4_DIMENSIONS_PROMPT.format(
                question_text=question_text,
                options_text=options_text,
                context_text=ctx_text,
                parent_label=l3_node.label,
                parent_id=l3_node.id,
                candidates_text=candidates_text,
            )
            resp4 = self.llm_client.complete(p4, system_prompt=SYSTEM_PROMPT)
            selected_attributes = resp4.get("selected_attributes", [])
            l4_reasoning = resp4.get("reasoning", "")

            selected_dim_ids = []
            for item in selected_attributes:
                if isinstance(item, dict):
                    dim_id = item.get("id")
                    reasoning = item.get("reasoning", "")
                    strength = item.get("relevance_strength", "high")
                elif isinstance(item, str):
                    dim_id = item
                    reasoning = "Identified as relevant by LLM."
                    strength = "high"
                else:
                    continue

                if dim_id and dim_id in dim_map and dim_id not in seen_dim_ids:
                    seen_dim_ids.add(dim_id)
                    selected_dim_ids.append(dim_id)
                    dim_node = dim_map[dim_id]
                    dependencies.append(
                        AttributeDependency(
                            dimension_id=dim_node.id,
                            dimension_label=dim_node.label,
                            path=dim_node.get_path(use_labels=False),
                            path_label=dim_node.get_path(use_labels=True),
                            category=dim_node.category,
                            description=dim_node.description,
                            values=dim_node.values,
                            reasoning=reasoning,
                            relevance_strength=strength,
                        )
                    )

            traversal_log.append({
                "level": 4,
                "parent_id": l3_node.id,
                "evaluated_count": len(dim_children),
                "selected_ids": selected_dim_ids,
                "reasoning": l4_reasoning,
            })

        self._log(f"  [Layer 4 Selection] Finished. Extracted {len(dependencies)} leaf attributes.")

        return QuestionDependencyResult(
            question_id=question_id,
            question_text=question_text,
            options=options or [],
            dependencies=dependencies,
            traversal_log=traversal_log,
        )

    def extract_for_survey(
        self,
        questions: List[Union[Dict[str, Any], str]],
        survey_id: str = "survey_1",
        survey_title: str = "Survey Task",
        context_text: Optional[str] = None,
    ) -> SurveyDependencyResult:
        """Extract attribute dependencies for an entire list of survey questions."""
        self._log(f"\n=======================================================")
        self._log(f"Processing Survey: '{survey_title}' ({len(questions)} sub-questions)")
        self._log(f"=======================================================")

        results: List[QuestionDependencyResult] = []
        for i, q in enumerate(questions, 1):
            if isinstance(q, dict):
                q_id = str(q.get("id", f"q{i}"))
                q_text = q.get("prompt") or q.get("question") or q.get("text", "")
                options = q.get("options") or []
                if options and isinstance(options[0], dict):
                    options = [opt.get("label") or opt.get("id", "") for opt in options]
            else:
                q_id = f"q{i}"
                q_text = str(q)
                options = []

            res = self.extract_for_question(
                question_text=q_text,
                question_id=q_id,
                options=options,
                context_text=context_text,
            )
            results.append(res)

        survey_res = SurveyDependencyResult(
            survey_id=survey_id,
            survey_title=survey_title,
            questions=results,
        )

        self._log(f"\n[Survey Analysis Completed] Extracted {len(survey_res.all_unique_dimensions)} "
                  f"unique persona attributes across {len(questions)} questions.")

        return survey_res


if __name__ == "__main__":
    pass 