import pytest
from playground.model_client import build_json_client
from playground.openai_client import OpenAIChatClient

def test_local_qwen_client_init():
    client = build_json_client("local/qwen3-14b")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "Qwen3-14B"
    assert client.provider == "local"
    assert client.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}

def test_local_qwen_live_complete():
    client = build_json_client("local/qwen3-14b")
    res = client.complete_json(
        system="You are a JSON answering assistant.",
        user="Respond with a JSON object containing key 'status' with value 'active'."
    )
    assert isinstance(res, dict)
    assert res.get("status") == "active"
