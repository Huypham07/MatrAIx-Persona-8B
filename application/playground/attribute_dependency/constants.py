from pathlib import Path

# Repository root (auto-detected)
REPO_ROOT = Path(__file__).resolve().parents[3]
FULL_DIMENSION = str(REPO_ROOT / "persona" / "schema" / "dimensions.json")
PERSONA_TAXONOMY = str(REPO_ROOT / "persona" / "schema" / "persona_taxonomy.json")
TAXONOMY_TREE_CACHE = str(REPO_ROOT / "persona" / "schema" / "persona_taxonomy_tree.json")

