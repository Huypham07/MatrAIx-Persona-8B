"""Attribute dependency package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dependency_extractor import (
        AttributeDependency,
        HierarchicalAttributePruner,
        QuestionDependencyResult,
        SurveyDependencyResult,
    )
    from .llm_client import BaseLLMClient, MockLLMClient, OpenAILLMClient
    from .load_tree import (
        PersonaTaxonomyTree,
        TreeNode,
        build_and_save_taxonomy_tree,
        build_full_stratified_tree,
        build_taxonomy_tree,
        load_or_build_taxonomy_tree,
        load_taxonomy_tree,
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
    "process_task_attribute_dependencies",
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
        elif name in ["BaseLLMClient", "OpenAILLMClient", "MockLLMClient"]:
            from . import llm_client
            return getattr(llm_client, name)
        elif name in ["process_task_attribute_dependencies"]:
            from . import task_processor
            return getattr(task_processor, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")




