import pytest
from playground.inprocess.chatbot_eval import DirectApplicationSession
from playground.types import PlaygroundConfig

def test_chatbot_sut_fallback_live():
    config = PlaygroundConfig(
        application_id="meal_planning_nutrition",
        application_context="meal_planning",
        persona_model="local/qwen3-14b"
    )
    session = DirectApplicationSession(config)
    turn1 = session.run_turn_sync("Hi! I have $30 for a 3-day meal plan and I am allergic to peanuts.")
    assert turn1["assistantMessage"] != ""
    assert turn1["userMessage"] == "Hi! I have $30 for a 3-day meal plan and I am allergic to peanuts."
    print("\nChatbot Assistant Reply:", turn1["assistantMessage"])
