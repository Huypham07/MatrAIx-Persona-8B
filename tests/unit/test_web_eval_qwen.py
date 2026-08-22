import pytest
from pathlib import Path
from playground.inprocess.web_eval import InprocessWebEvalRunner
from playground.harbor.web_eval import WebEvalTask, HarborWebEvalConfig
from playground.types import Persona

def test_web_eval_runner_live():
    persona = Persona(
        id="test_student",
        name="Alex Rivera",
        summary="A computer science student seeking advanced algorithms courses.",
        context="I am a CS student at university. I want to find free online courses on distributed systems and advanced algorithms.",
        goal="Select the best distributed systems course on MIT OCW"
    )
    task = WebEvalTask(
        id="web-mit-ocw-course-choice",
        title="MIT OCW Course Choice",
        site_name="MIT OpenCourseWare",
        site_url="https://ocw.mit.edu",
        task_path=Path("application/tasks/web_mit-ocw-course-choice"),
        description="Find and choose the most suitable computer science course on MIT OCW."
    )
    runner = InprocessWebEvalRunner()
    result = runner(
        persona=persona,
        task=task,
        config=HarborWebEvalConfig(persona_model="local/qwen3-14b"),
        created_at="2026-08-22T00:00:00Z"
    )
    assert result.web_result.valid is True
    assert 1 <= result.web_result.need_satisfaction <= 10
    assert 1 <= result.web_result.overall_experience_rating <= 10
    assert len(result.web_result.reason) >= 20
    print("\nWeb Result:", result.web_result.to_dict())
