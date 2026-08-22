import pytest
from playground.inprocess.survey_eval import InprocessSurveyEvalRunner
from playground.types import Persona
from backend.service.survey_types import SurveyInstrument, SurveyQuestion, SurveyEvalConfig

def test_survey_eval_runner_live():
    persona = Persona(
        id="test_budget_mom",
        name="Sarah Jenkins",
        summary="A mother of two living on a tight monthly budget.",
        context="I am a budget-conscious mother of two living in Ohio. I track every dollar and look for discounts on toys.",
        goal="Find affordable family board games"
    )
    instrument = SurveyInstrument(
        id="survey_price_sensitivity",
        title="Candy Land Price Sensitivity Survey",
        questions=[
            SurveyQuestion(
                id="price_reaction",
                prompt="The board game Candy Land has increased in price from $15 to $25. How do you respond?",
                type="single_choice",
                options=["fair_buy", "hesitate", "refuse_buy"],
                required=True
            ),
            SurveyQuestion(
                id="satisfaction_rating",
                prompt="Rate your overall price satisfaction on a 1-5 scale.",
                type="likert",
                min_value=1,
                max_value=5,
                required=True
            )
        ]
    )
    runner = InprocessSurveyEvalRunner()
    result = runner(
        persona=persona,
        instrument=instrument,
        config=SurveyEvalConfig(persona_model="local/qwen3-14b"),
        created_at="2026-08-22T00:00:00Z",
        persona_yaml_path=""
    )
    assert len(result.answers) == 2
    assert result.metrics.num_answered == 2
    assert result.metrics.num_questions == 2
    assert result.metrics.mean_likert is not None
    print("\nSurvey answers:", [a.to_dict() for a in result.answers])
    print("Metrics:", result.metrics.to_dict())
