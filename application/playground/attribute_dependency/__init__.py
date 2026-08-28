"""Attribute dependency package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adherence_evaluator import (
        AttributeAdherenceVerdict,
        PersonaAttributeAdherenceEvaluator,
        QuestionAdherenceResult,
        SurveyAdherenceResult,
    )
    from .dependency_extractor import (
        AttributeDependency,
        HierarchicalAttributePruner,
        QuestionDependencyResult,
        SurveyDependencyResult,
    )
    from .llm_client import BaseLLMClient, MockLLMClient, OpenAILLMClient, build_llm_client_for_model
    from .load_tree import (
        PersonaTaxonomyTree,
        TreeNode,
        build_and_save_taxonomy_tree,
        build_full_stratified_tree,
        build_taxonomy_tree,
        load_or_build_taxonomy_tree,
        load_taxonomy_tree,
    )
    from .persona_filter import (
        CORE_DEMOGRAPHIC_ATTRIBUTES,
        find_task_attribute_dependencies_path,
        load_task_unique_attributes,
        prune_persona_dimensions,
        prune_persona_object,
    )
    from .task_processor import process_task_attribute_dependencies

__all__ = [
    "TreeNode",
    "PersonaTaxonomyTree",
    "build_taxonomy_tree",
    "build_and_save_taxonomy_tree",
    "load_taxonomy_tree",
    "load_or_build_taxonomy_tree",
    "build_full_stratified_tree",
    "AttributeDependency",
    "QuestionDependencyResult",
    "SurveyDependencyResult",
    "HierarchicalAttributePruner",
    "BaseLLMClient",
    "OpenAILLMClient",
    "MockLLMClient",
    "build_llm_client_for_model",
    "process_task_attribute_dependencies",
    "PersonaAttributeAdherenceEvaluator",
    "SurveyAdherenceResult",
    "QuestionAdherenceResult",
    "AttributeAdherenceVerdict",
    "find_task_attribute_dependencies_path",
    "load_task_unique_attributes",
    "prune_persona_dimensions",
    "prune_persona_object",
    "CORE_DEMOGRAPHIC_ATTRIBUTES",
]


def __getattr__(name: str):
    if name in __all__:
        if name in [
            "TreeNode",
            "PersonaTaxonomyTree",
            "build_taxonomy_tree",
            "build_and_save_taxonomy_tree",
            "load_taxonomy_tree",
            "load_or_build_taxonomy_tree",
            "build_full_stratified_tree",
        ]:
            from . import load_tree

            return getattr(load_tree, name)
        elif name in [
            "AttributeDependency",
            "QuestionDependencyResult",
            "SurveyDependencyResult",
            "HierarchicalAttributePruner",
        ]:
            from . import dependency_extractor

            return getattr(dependency_extractor, name)
        elif name in ["BaseLLMClient", "OpenAILLMClient", "MockLLMClient", "build_llm_client_for_model"]:
            from . import llm_client

            return getattr(llm_client, name)
        elif name in ["process_task_attribute_dependencies"]:
            from . import task_processor

            return getattr(task_processor, name)
        elif name in [
            "PersonaAttributeAdherenceEvaluator",
            "SurveyAdherenceResult",
            "QuestionAdherenceResult",
            "AttributeAdherenceVerdict",
        ]:
            from . import adherence_evaluator

            return getattr(adherence_evaluator, name)
        elif name in [
            "find_task_attribute_dependencies_path",
            "load_task_unique_attributes",
            "prune_persona_dimensions",
            "prune_persona_object",
            "CORE_DEMOGRAPHIC_ATTRIBUTES",
        ]:
            from . import persona_filter

            return getattr(persona_filter, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")




