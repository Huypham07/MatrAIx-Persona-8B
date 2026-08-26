"""Tests for task-level persona_dimensions.yaml loading and filtering."""

from pathlib import Path
import tempfile
import yaml
from matraix.persona_dimension_catalog import (
    load_task_persona_dimensions,
    resolve_included_fields,
    collect_dimension_items,
    build_dimension_narrative,
)
from playground.types import Persona
from playground.user_sim.prompt import render_persona_block


def test_load_task_persona_dimensions_yaml():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        yaml_file = tmppath / "persona_dimensions.yaml"
        yaml_file.write_text(
            """
dimensions:
  - age
  - gender
  - occupation
  - price_sensitivity
""",
            encoding="utf-8",
        )
        loaded = load_task_persona_dimensions(tmppath)
        assert loaded.get("dimensions") == ["age", "gender", "occupation", "price_sensitivity"]


def test_dimension_filtering_with_task_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        yaml_file = tmppath / "persona_dimensions.yaml"
        yaml_file.write_text(
            """
dimensions:
  - age
  - gender
  - price_sensitivity
""",
            encoding="utf-8",
        )

        sample_dimensions = {
            "demo_age": 32,
            "demo_gender": "Female",
            "demo_occupation": "Software Engineer",
            "price_sensitivity": "High",
            "tech_savviness": "Advanced",
        }

        # Without filter: includes all non-null non-default
        all_items = collect_dimension_items(sample_dimensions)
        all_dim_ids = [d[0] for section in all_items.values() for d in section]
        assert "demo_occupation" in all_dim_ids

        # With task_dir: only specified fields
        filtered_items = collect_dimension_items(sample_dimensions, task_dir=tmppath)
        filtered_dim_ids = [d[0] for section in filtered_items.values() for d in section]
        assert "demo_age" in filtered_dim_ids
        assert "demo_gender" in filtered_dim_ids
        assert "price_sensitivity" in filtered_dim_ids
        assert "demo_occupation" not in filtered_dim_ids
        assert "tech_savviness" not in filtered_dim_ids


def test_render_persona_block_with_task_dimensions():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Create a sample persona yaml
        persona_file = tmppath / "persona.yaml"
        persona_file.write_text(
            """
schema_version: "v1"
display_name: "Alice"
dimensions:
  demo_age: 28
  demo_gender: "Female"
  demo_occupation: "Designer"
  price_sensitivity: "Moderate"
  hobbies: "Painting, Gaming"
""",
            encoding="utf-8",
        )

        # Create a task dir with persona_dimensions.yaml
        task_dir = tmppath / "my_task"
        task_dir.mkdir()
        (task_dir / "persona_dimensions.yaml").write_text(
            """
dimensions:
  - age
  - price_sensitivity
""",
            encoding="utf-8",
        )

        persona = Persona(
            id="0001",
            name="Alice",
            persona_path=str(persona_file),
            dimensions={"demo_age": 28, "demo_gender": "Female", "demo_occupation": "Designer", "price_sensitivity": "Moderate"},
            context=None,
        )

        rendered = render_persona_block(persona, persona_yaml_path=str(persona_file), task_dir=task_dir)
        assert "28" in rendered
        assert "Moderate" in rendered
        assert "Designer" not in rendered
        assert "Female" not in rendered


def test_chatbot_prompt_bundle_with_task_dimensions():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        persona_file = tmppath / "persona.yaml"
        persona_file.write_text(
            """
schema_version: "v1"
display_name: "Bob"
dimensions:
  demo_age: 45
  demo_occupation: "Nutritionist"
  demo_gender: "Male"
  hobbies: "Cooking, Cycling"
""",
            encoding="utf-8",
        )

        task_dir = tmppath / "chat_meal_planning"
        task_dir.mkdir()
        (task_dir / "persona_dimensions.yaml").write_text(
            """
dimensions:
  - age
  - occupation
""",
            encoding="utf-8",
        )

        persona = Persona(
            id="0002",
            name="Bob",
            persona_path=str(persona_file),
            dimensions={"demo_age": 45, "demo_occupation": "Nutritionist", "demo_gender": "Male", "hobbies": "Cooking, Cycling"},
            context=None,
        )

        from playground.user_sim.prompt import prompt_bundle
        bundle = prompt_bundle(persona, persona_yaml_path=str(persona_file), task_dir=task_dir)
        assert "45" in bundle["personaPrompt"]
        assert "Nutritionist" in bundle["personaPrompt"]
        assert "Cycling" not in bundle["personaPrompt"]
        assert "Male" not in bundle["personaPrompt"]
