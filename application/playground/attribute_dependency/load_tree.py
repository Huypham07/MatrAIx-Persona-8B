from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

try:
    from .constants import FULL_DIMENSION, PERSONA_TAXONOMY, TAXONOMY_TREE_CACHE
except ImportError:
    from constants import FULL_DIMENSION, PERSONA_TAXONOMY, TAXONOMY_TREE_CACHE


@dataclass
class TreeNode:
    """A node representing an entity in the Persona Taxonomy tree.

    Hierarchy levels:
      0: Root ('root')
      1: Layer 1 Group (e.g., 'background', 'psychology', 'capability', ...)
      2: Layer 2 Subgroup (e.g., 'demographics', 'language', 'education', ...)
      3: Layer 3 Category (e.g., 'core_demographics', 'family', 'academic_background', ...)
      4: Dimension / Attribute leaf (e.g., 'age_bracket', 'region', 'gender_identity', ...)
    """
    id: str
    label: str
    level: int = 0
    node_type: str = "node"  # "root", "layer_1", "layer_2", "layer_3", "dimension"
    parent: Optional[TreeNode] = field(default=None, repr=False)
    children: List[TreeNode] = field(default_factory=list)

    # Metadata for Dimension (Level 4 / Leaf)
    values: List[str] = field(default_factory=list)
    category: Optional[str] = None
    description: Optional[str] = None
    phrase: Optional[str] = None
    default_value: Optional[Any] = None
    index: Optional[int] = None

    # Additional metadata (e.g. expected_count, mapping rules)
    expected_count: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_leaf(self) -> bool:
        """True if this node has no children."""
        return len(self.children) == 0

    @property
    def is_dimension(self) -> bool:
        """True if this node is a persona dimension/attribute."""
        return self.node_type == "dimension"

    def add_child(self, child: TreeNode) -> TreeNode:
        """Add a child node and set its parent reference."""
        child.parent = self
        self.children.append(child)
        return child

    def get_path_list(self, use_labels: bool = False, include_root: bool = False) -> List[str]:
        """Returns the list of identifiers/labels from root down to this node."""
        path: List[str] = []
        curr: Optional[TreeNode] = self
        while curr is not None:
            if curr.level == 0 and not include_root:
                curr = curr.parent
                continue
            path.append(curr.label if use_labels else curr.id)
            curr = curr.parent
        path.reverse()
        return path

    def get_path(self, use_labels: bool = False, separator: str = " > ", include_root: bool = False) -> str:
        """Get formatted path string.

        Example:
          - use_labels=False: 'background > demographics > core_demographics > age_bracket'
          - use_labels=True:  'Background > Demographics > Core Demographics > Age bracket'
        """
        return separator.join(self.get_path_list(use_labels=use_labels, include_root=include_root))

    def get_leaves(self) -> List[TreeNode]:
        """Collect all leaf dimension nodes under this subtree."""
        if self.is_leaf:
            return [self] if self.is_dimension else []
        leaves: List[TreeNode] = []
        for child in self.children:
            leaves.extend(child.get_leaves())
        return leaves

    def find_by_id(self, target_id: str) -> Optional[TreeNode]:
        """Search recursively for a node with the given ID."""
        if self.id == target_id:
            return self
        for child in self.children:
            found = child.find_by_id(target_id)
            if found is not None:
                return found
        return None

    def to_dict(self, include_values: bool = True, include_metadata: bool = True) -> Dict[str, Any]:
        """Serialize subtree to a nested dictionary."""
        data: Dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "level": self.level,
            "node_type": self.node_type,
        }
        if self.expected_count is not None:
            data["expected_count"] = self.expected_count
        if self.is_dimension:
            if self.category is not None:
                data["category"] = self.category
            if self.description is not None:
                data["description"] = self.description
            if self.phrase is not None:
                data["phrase"] = self.phrase
            if self.index is not None:
                data["index"] = self.index
            if self.default_value is not None:
                data["defaultValue"] = self.default_value
            if include_values:
                data["values"] = self.values
        if include_metadata and self.metadata:
            data["metadata"] = self.metadata
        if self.children:
            data["children"] = [
                c.to_dict(include_values=include_values, include_metadata=include_metadata)
                for c in self.children
            ]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent: Optional[TreeNode] = None) -> TreeNode:
        """Deserialize a dictionary back into a TreeNode hierarchy."""
        node = cls(
            id=data["id"],
            label=data.get("label", data["id"]),
            level=data.get("level", 0),
            node_type=data.get("node_type", "node"),
            parent=parent,
            values=data.get("values", []),
            category=data.get("category"),
            description=data.get("description"),
            phrase=data.get("phrase"),
            default_value=data.get("defaultValue"),
            index=data.get("index"),
            expected_count=data.get("expected_count"),
            metadata=data.get("metadata", {}),
        )
        for child_data in data.get("children", []):
            child_node = cls.from_dict(child_data, parent=node)
            node.children.append(child_node)
        return node

    def render_tree(
        self,
        max_depth: Optional[int] = None,
        show_values_count: bool = True,
        prefix: str = "",
        ascii_only: bool = False,
    ) -> str:
        """Render a clean ASCII/Unicode hierarchical tree representation."""
        lines = []
        info = f" ({len(self.values)} values)" if self.is_dimension and show_values_count else ""
        if self.expected_count is not None and not self.is_dimension and self.level > 0:
            info = f" [{self.expected_count} dims]"
        lines.append(f"{prefix}{self.label} ({self.id}){info}")

        if max_depth is not None and self.level >= max_depth:
            return "\n".join(lines)

        connector_last = "\\-- " if ascii_only else "└── "
        connector_branch = "+-- " if ascii_only else "├── "
        pipe_indent = "    " if ascii_only else "│   "

        for i, child in enumerate(self.children):
            is_last = (i == len(self.children) - 1)
            connector = connector_last if is_last else connector_branch
            child_prefix = prefix + ("    " if is_last else pipe_indent)
            child_str = child.render_tree(
                max_depth=max_depth,
                show_values_count=show_values_count,
                prefix=child_prefix,
                ascii_only=ascii_only,
            )
            child_lines = child_str.split("\n")
            child_lines[0] = prefix + connector + child_lines[0][len(child_prefix):]
            lines.extend(child_lines)

        return "\n".join(lines)

    def __repr__(self) -> str:
        if self.is_dimension:
            return f"<TreeNode [dimension] id='{self.id}' label='{self.label}' values={len(self.values)}>"
        return f"<TreeNode [{self.node_type}] id='{self.id}' label='{self.label}' children={len(self.children)}>"


class PersonaTaxonomyTree:
    """Container and query interface for the complete Persona Taxonomy Tree."""

    def __init__(self, root: TreeNode):
        self.root = root
        self._nodes_by_id: Dict[str, TreeNode] = {}
        self._dimensions_by_id: Dict[str, TreeNode] = {}
        self._paths_by_id: Dict[str, str] = {}
        self._build_indexes(self.root)

    def _build_indexes(self, node: TreeNode) -> None:
        if node.id != "root":
            self._nodes_by_id[node.id] = node
            if node.is_dimension:
                self._dimensions_by_id[node.id] = node
                self._paths_by_id[node.id] = node.get_path(use_labels=False)

        for child in node.children:
            self._build_indexes(child)

    def get(self, node_id: str) -> Optional[TreeNode]:
        """Get any node (Group, Subgroup, Category, Dimension) by its ID."""
        return self._nodes_by_id.get(node_id)

    def get_dimension(self, dimension_id: str) -> Optional[TreeNode]:
        """Get a dimension leaf node by dimension ID."""
        return self._dimensions_by_id.get(dimension_id)

    def get_path(self, node_id: str, use_labels: bool = False, separator: str = " > ") -> Optional[str]:
        """Get full hierarchical path for any node ID."""
        node = self._nodes_by_id.get(node_id)
        if node is not None:
            return node.get_path(use_labels=use_labels, separator=separator)
        return None

    def get_all_paths(self, use_labels: bool = False, separator: str = " > ") -> Dict[str, str]:
        """Returns dictionary mapping {dimension_id: 'layer1 > layer2 > layer3 > dim_id'}."""
        return {
            dim_id: node.get_path(use_labels=use_labels, separator=separator)
            for dim_id, node in self._dimensions_by_id.items()
        }

    def find_by_path(self, path: Union[str, List[str]], separator: str = " > ") -> Optional[TreeNode]:
        """Find a node by path string or list of IDs/labels.

        Examples:
          - "background > demographics > core_demographics > age_bracket"
          - "Background > Demographics > Core Demographics > Age bracket"
          - "background/demographics/core_demographics/age_bracket"
        """
        if isinstance(path, str):
            if separator in path:
                parts = [p.strip() for p in path.split(separator)]
            elif "/" in path:
                parts = [p.strip() for p in path.split("/")]
            elif ">" in path:
                parts = [p.strip() for p in path.split(">")]
            else:
                parts = [path.strip()]
        else:
            parts = list(path)

        curr = self.root
        for part in parts:
            matched = False
            for child in curr.children:
                if child.id.lower() == part.lower() or child.label.lower() == part.lower():
                    curr = child
                    matched = True
                    break
            if not matched:
                return None
        return curr

    def to_dict(self, include_values: bool = True, include_metadata: bool = True) -> Dict[str, Any]:
        """Serialize the full tree to a JSON-compatible dictionary."""
        return self.root.to_dict(include_values=include_values, include_metadata=include_metadata)

    def save_to_json(self, output_path: Optional[Union[str, Path]] = None, indent: int = 2) -> Path:
        """Save the tree structure to a JSON file."""
        target_path = Path(output_path or TAXONOMY_TREE_CACHE)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)
        return target_path

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PersonaTaxonomyTree:
        """Create a PersonaTaxonomyTree instance from a serialized dictionary."""
        root = TreeNode.from_dict(data)
        return cls(root)

    @classmethod
    def from_json(cls, json_path: Optional[Union[str, Path]] = None) -> PersonaTaxonomyTree:
        """Load a PersonaTaxonomyTree directly from a cached JSON file."""
        target_path = Path(json_path or TAXONOMY_TREE_CACHE)
        if not target_path.exists():
            raise FileNotFoundError(f"Taxonomy tree JSON cache not found at: {target_path}")
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_flat_records(self) -> List[Dict[str, Any]]:
        """Export flat records with all hierarchy levels for tabular data or DataFrame."""
        records = []
        for dim_id, dim_node in self._dimensions_by_id.items():
            path_nodes = []
            curr: Optional[TreeNode] = dim_node
            while curr and curr.level > 0:
                path_nodes.append(curr)
                curr = curr.parent
            path_nodes.reverse()

            l1 = path_nodes[0] if len(path_nodes) > 0 else None
            l2 = path_nodes[1] if len(path_nodes) > 1 else None
            l3 = path_nodes[2] if len(path_nodes) > 2 else None

            records.append({
                "dimension_id": dim_node.id,
                "dimension_label": dim_node.label,
                "schema_category": dim_node.category,
                "layer_1_id": l1.id if l1 else None,
                "layer_1_label": l1.label if l1 else None,
                "layer_2_id": l2.id if l2 else None,
                "layer_2_label": l2.label if l2 else None,
                "layer_3_id": l3.id if l3 else None,
                "layer_3_label": l3.label if l3 else None,
                "path_id": dim_node.get_path(use_labels=False),
                "path_label": dim_node.get_path(use_labels=True),
                "values": dim_node.values,
                "description": dim_node.description,
                "phrase": dim_node.phrase,
                "index": dim_node.index,
            })
        return records

    def print_tree(
        self,
        max_depth: Optional[int] = 3,
        show_values_count: bool = True,
        ascii_only: bool = False,
    ) -> None:
        """Print tree visualization to stdout."""
        try:
            print(self.root.render_tree(
                max_depth=max_depth,
                show_values_count=show_values_count,
                ascii_only=ascii_only,
            ))
        except UnicodeEncodeError:
            # Fallback for terminals with ASCII / cp1252 limitations
            print(self.root.render_tree(
                max_depth=max_depth,
                show_values_count=show_values_count,
                ascii_only=True,
            ))

    def summary(self) -> Dict[str, int]:
        """Returns counts of nodes at each level."""
        return {
            "layer_1_groups": len(self.root.children),
            "layer_2_subgroups": sum(len(l1.children) for l1 in self.root.children),
            "layer_3_categories": sum(len(l2.children) for l1 in self.root.children for l2 in l1.children),
            "dimensions": len(self._dimensions_by_id),
        }

    def __getitem__(self, node_id: str) -> TreeNode:
        node = self.get(node_id)
        if node is None:
            raise KeyError(f"Node '{node_id}' not found in Persona Taxonomy Tree.")
        return node

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes_by_id

    def __len__(self) -> int:
        return len(self._dimensions_by_id)

    def __iter__(self) -> Iterator[TreeNode]:
        """Iterate over all dimension leaf nodes."""
        return iter(self._dimensions_by_id.values())


def build_taxonomy_tree(
    dimension_path: Optional[Union[str, Path]] = None,
    taxonomy_path: Optional[Union[str, Path]] = None,
) -> PersonaTaxonomyTree:
    """Build the complete 4-level Persona Taxonomy Tree from schema JSON files.

    Structure:
      - Root
        - Layer 1 (5 Groups: Background, Psychology, Capability, Behavior & Interaction, Lifestyle & Health)
          - Layer 2 (16 Subgroups: Demographics, Language, Education, ...)
            - Layer 3 (55 Category Groups: Core Demographics, Family, ...)
              - Dimension (1290 Leaf Attributes: age_bracket, region, ...)
    """
    dim_p = Path(dimension_path or FULL_DIMENSION)
    tax_p = Path(taxonomy_path or PERSONA_TAXONOMY)

    with open(dim_p, "r", encoding="utf-8") as f:
        dimensions_data = json.load(f)
    with open(tax_p, "r", encoding="utf-8") as f:
        taxonomy_data = json.load(f)

    # Index dimensions by ID and by Category
    dimensions_list = dimensions_data.get("dimensions", [])
    dim_by_id: Dict[str, Dict[str, Any]] = {d["id"]: d for d in dimensions_list}
    dim_by_category: Dict[str, List[Dict[str, Any]]] = {}
    for d in dimensions_list:
        cat = d.get("category", "")
        dim_by_category.setdefault(cat, []).append(d)

    root = TreeNode(
        id="root",
        label=taxonomy_data.get("name", "Persona Taxonomy Root"),
        level=0,
        node_type="root",
        expected_count=taxonomy_data.get("expected_attribute_count", 1290),
        metadata={
            "taxonomy_version": taxonomy_data.get("taxonomy_version"),
            "source_schema": taxonomy_data.get("source_schema"),
            "expected_structure": taxonomy_data.get("expected_structure"),
        },
    )

    for l1_data in taxonomy_data.get("hierarchy", []):
        l1_node = TreeNode(
            id=l1_data["id"],
            label=l1_data.get("label", l1_data["id"]),
            level=1,
            node_type="layer_1",
            expected_count=l1_data.get("expected_count"),
        )
        root.add_child(l1_node)

        for l2_data in l1_data.get("children", []):
            l2_node = TreeNode(
                id=l2_data["id"],
                label=l2_data.get("label", l2_data["id"]),
                level=2,
                node_type="layer_2",
                expected_count=l2_data.get("expected_count"),
            )
            l1_node.add_child(l2_node)

            for l3_data in l2_data.get("children", []):
                l3_node = TreeNode(
                    id=l3_data["id"],
                    label=l3_data.get("label", l3_data["id"]),
                    level=3,
                    node_type="layer_3",
                    expected_count=l3_data.get("expected_count"),
                    metadata={"mapping": l3_data.get("mapping")},
                )
                l2_node.add_child(l3_node)

                # Resolve dimensions for Layer 3 node based on mapping mode
                mapping = l3_data.get("mapping", {})
                mode = mapping.get("mode", "all_in_categories")
                schema_categories = mapping.get("schema_categories", [])
                resolved_dims: List[Dict[str, Any]] = []

                if mode == "all_in_categories":
                    for cat in schema_categories:
                        resolved_dims.extend(dim_by_category.get(cat, []))
                elif mode == "explicit_attributes":
                    attr_ids = mapping.get("attribute_ids", [])
                    for aid in attr_ids:
                        if aid in dim_by_id:
                            resolved_dims.append(dim_by_id[aid])

                for d in resolved_dims:
                    dim_node = TreeNode(
                        id=d["id"],
                        label=d.get("label", d["id"]),
                        level=4,
                        node_type="dimension",
                        values=d.get("values", []),
                        category=d.get("category"),
                        description=d.get("description"),
                        phrase=d.get("phrase"),
                        default_value=d.get("defaultValue"),
                        index=d.get("index"),
                    )
                    l3_node.add_child(dim_node)

    return PersonaTaxonomyTree(root)


def build_and_save_taxonomy_tree(
    output_path: Optional[Union[str, Path]] = None,
    dimension_path: Optional[Union[str, Path]] = None,
    taxonomy_path: Optional[Union[str, Path]] = None,
) -> PersonaTaxonomyTree:
    """Build the taxonomy tree from raw schema files and save to a JSON cache file."""
    tree = build_taxonomy_tree(dimension_path=dimension_path, taxonomy_path=taxonomy_path)
    saved_path = tree.save_to_json(output_path=output_path)
    print(f"[build_and_save_taxonomy_tree] Saved tree JSON to: {saved_path}")
    return tree


def load_taxonomy_tree(json_path: Optional[Union[str, Path]] = None) -> PersonaTaxonomyTree:
    """Load the pre-built taxonomy tree from a JSON cache file."""
    return PersonaTaxonomyTree.from_json(json_path=json_path)


def load_or_build_taxonomy_tree(
    cache_path: Optional[Union[str, Path]] = None,
    force_rebuild: bool = False,
    dimension_path: Optional[Union[str, Path]] = None,
    taxonomy_path: Optional[Union[str, Path]] = None,
) -> PersonaTaxonomyTree:
    """Load tree from cached JSON file if exists, otherwise build, save to JSON, and return.

    Args:
        cache_path: Path to the cached JSON file (defaults to TAXONOMY_TREE_CACHE).
        force_rebuild: If True, forces re-parsing raw schema files and re-saving cache.
        dimension_path: Path to dimensions.json (optional).
        taxonomy_path: Path to persona_taxonomy.json (optional).

    Returns:
        PersonaTaxonomyTree instance.
    """
    target_cache = Path(cache_path or TAXONOMY_TREE_CACHE)

    if not force_rebuild and target_cache.exists():
        return PersonaTaxonomyTree.from_json(target_cache)

    return build_and_save_taxonomy_tree(
        output_path=target_cache,
        dimension_path=dimension_path,
        taxonomy_path=taxonomy_path,
    )


def build_full_stratified_tree(
    dimension_path: Optional[Union[str, Path]] = None,
    taxonomy_path: Optional[Union[str, Path]] = None,
    cache_path: Optional[Union[str, Path]] = None,
    force_rebuild: bool = False,
) -> PersonaTaxonomyTree:
    """Build or load full stratified tree with automatic caching."""
    return load_or_build_taxonomy_tree(
        cache_path=cache_path,
        force_rebuild=force_rebuild,
        dimension_path=dimension_path,
        taxonomy_path=taxonomy_path,
    )


if __name__ == "__main__":
    # Test load_or_build_taxonomy_tree: first run will build and cache; subsequent runs load from JSON!
    tree = load_or_build_taxonomy_tree(force_rebuild=True)
    print("=== Persona Taxonomy Tree Summary ===")
    print(tree.summary())
    print("\n=== Path Examples ===")
    age_node = tree.get_dimension("age_bracket")
    if age_node:
        print("ID Path:   ", age_node.get_path(use_labels=False))
        print("Label Path:", age_node.get_path(use_labels=True))
        print("Values:    ", age_node.values)

    # Test loading directly from the cached json file
    print("\n=== Loading directly from cached JSON ===")
    cached_tree = load_taxonomy_tree()
    print("Cached tree loaded! Dimensions count:", len(cached_tree))
    print("age_bracket path from cache:", cached_tree["age_bracket"].get_path())


    
    

