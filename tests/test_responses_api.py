from __future__ import annotations

from copy import deepcopy
import json

import httpx
from openai import OpenAI
import pytest

import agent
import responses_api
import summary
from tools import TOOLS
from tools.db import get_conn


def message(text="Gotowe.", *, refusal=False):
    part = ({"type": "refusal", "refusal": text} if refusal else
            {"type": "output_text", "text": text, "annotations": []})
    return {"id": "msg_1", "type": "message", "role": "assistant",
            "status": "completed", "content": [part]}


def call(name, arguments="{}", call_id="call_1"):
    return {"id": "fc_" + call_id, "type": "function_call", "call_id": call_id,
            "name": name, "arguments": arguments, "status": "completed"}


def response(output, status="completed"):
    return {"id": "resp_test", "object": "response", "created_at": 1,
            "model": "gpt-6.1-sol", "status": status, "output": output,
            "error": None,
            "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
            "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}}


@pytest.fixture
def mock_api(monkeypatch):
    """Use the real SDK/serialization over a local HTTP mock; no API key/network."""
    def install(replies):
        pending = list(replies)
        requests = []

        def handle(request):
            assert request.method == "POST"
            assert request.url.path == "/v1/responses"
            requests.append(json.loads(request.content))
            assert pending, "Unexpected extra model request"
            return httpx.Response(200, json=pending.pop(0))

        def client(**options):
            return OpenAI(
                api_key="test-only", base_url="http://model.test/v1",
                http_client=httpx.Client(transport=httpx.MockTransport(handle)), **options,
            )

        monkeypatch.setattr(responses_api, "OpenAI", client)
        return requests
    return install


@pytest.fixture
def agent_context(monkeypatch, temp_db):
    monkeypatch.setattr(agent, "MODEL", "gpt-6.1-sol")
    monkeypatch.setattr(agent, "_build_system_message", lambda: ("System testowy", {}))
    monkeypatch.setenv("AGENT_REASONING_EFFORT", "low")
    monkeypatch.setenv("AGENT_MAX_OUTPUT_TOKENS", "8192")
    monkeypatch.setattr(agent.litellm, "completion", lambda **kwargs: pytest.fail("Unexpected Chat Completions request"))


@pytest.mark.parametrize("model, expected", [
    ("gpt-6.1-sol", True), ("openai/gpt-6.1-sol", True),
    ("gpt-6.1-sol-2026-09-29", True), ("gpt-5.4", False),
    ("gpt-5.6-sol", False), ("anthropic/claude-sonnet-4", False),
    ("azure/gpt-6.1-sol", False), ("other/gpt-6.1-sol", False),
])
def test_endpoint_routing(model, expected):
    assert responses_api.uses_responses(model) is expected


def test_multiple_tool_rounds_preserve_reasoning_and_record_usage(mock_api, agent_context, monkeypatch):
    reasoning = {"id": "rs_1", "type": "reasoning", "summary": [],
                 "encrypted_content": "encrypted-test-reasoning"}
    first = [reasoning, call("get_weight_trend", '{"days":7}'),
             call("update_patient_file", '{"filename":"pacjent.md","content":"test"}', "call_2")]
    requests = mock_api([
        response(first), response([call("get_recent_meals", '{"days":2}', "call_3")]),
        response([message("Odpowiedź końcowa.")]),
    ])
    executed = []
    monkeypatch.setattr(agent, "execute_tool", lambda name, args: executed.append((name, args)) or {"ok": True})
    original_tools = deepcopy(TOOLS)

    assert agent.run_agent("Pokaż dane", "test") == ("Odpowiedź końcowa.", True)
    assert len(executed) == 3
    assert executed[0] == ("get_weight_trend", {"days": 7})
    assert len(requests) == 3
    assert requests[1]["input"][2:5] == first
    assert [item["call_id"] for item in requests[2]["input"] if item.get("type") == "function_call_output"] == ["call_1", "call_2", "call_3"]
    for request in requests:
        assert request["model"] == "gpt-6.1-sol"
        assert request["store"] is False
        assert request["include"] == ["reasoning.encrypted_content"]
        assert request["reasoning"] == {"effort": "low"}
        assert request["max_output_tokens"] == 8192
        assert "previous_response_id" not in request
        assert all(tool["strict"] is False and "function" not in tool for tool in request["tools"])
    assert TOOLS == original_tools
    with get_conn() as conn:
        usage = conn.execute("SELECT SUM(prompt_tokens), SUM(completion_tokens), COUNT(*) FROM usage_stats").fetchone()
        history = conn.execute("SELECT role, content FROM conversations ORDER BY id").fetchall()
    assert tuple(usage) == (33, 21, 3)
    assert [(row["role"], row["content"]) for row in history] == [("user", "Pokaż dane"), ("assistant", "Odpowiedź końcowa.")]


def test_images_and_existing_history_work_with_prefixed_model(mock_api, agent_context, monkeypatch):
    monkeypatch.setattr(agent, "MODEL", "openai/gpt-6.1-sol")
    image = [{"type": "text", "text": "Posiłek"},
             {"type": "image_url", "image_url": {"url": "data:image/png;base64,dGVzdA==", "detail": "low"}}]
    original = deepcopy(image)
    agent.save_history("test", image, "Poprzedni posiłek.")
    requests = mock_api([response([message()])])

    assert agent.run_agent(image, "test") == ("Gotowe.", False)
    expected = [{"type": "input_text", "text": "Posiłek"},
                {"type": "input_image", "image_url": "data:image/png;base64,dGVzdA==", "detail": "low"}]
    assert requests[0]["input"][1]["content"] == expected
    assert requests[0]["input"][-1]["content"] == expected
    assert image == original
    assert agent.load_history("test")[-2]["content"] == original


def test_incomplete_response_never_executes_tools_or_saves_partial_history(mock_api, agent_context, monkeypatch):
    mock_api([response([call("log_meal", '{"name":')], status="incomplete")])
    monkeypatch.setattr(agent, "execute_tool", lambda *args: pytest.fail("Partial tool call executed"))
    with pytest.raises(RuntimeError, match="AGENT_MAX_OUTPUT_TOKENS"):
        agent.run_agent("test", "test")
    assert agent.load_history("test") == []
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_stats").fetchone()[0] == 1


def test_refusal_is_returned_as_text(mock_api, agent_context):
    mock_api([response([message("Nie mogę tego zrobić.", refusal=True)])])
    assert agent.run_agent("test", "test") == ("Nie mogę tego zrobić.", False)


def test_failed_response_does_not_execute_tools(mock_api, agent_context, monkeypatch):
    mock_api([response([call("log_meal")], status="failed")])
    monkeypatch.setattr(agent, "execute_tool", lambda *args: pytest.fail("Failed response executed"))
    with pytest.raises(RuntimeError, match="did not complete"):
        agent.run_agent("test", "test")
    assert agent.load_history("test") == []


def test_tool_round_limit_is_preserved(mock_api, agent_context, monkeypatch):
    monkeypatch.setattr(agent, "MAX_TOOL_ROUNDS", 2)
    monkeypatch.setattr(agent, "execute_tool", lambda *args: {"ok": True})
    requests = mock_api([response([call("get_hrv")]), response([call("get_hrv", call_id="call_2")])])
    answer, refresh = agent.run_agent("test", "test")
    assert "nie mogłem" in answer
    assert refresh is False
    assert len(requests) == 2
    assert agent.load_history("test")[-1]["content"] == answer


@pytest.mark.parametrize("model, options", [("gpt-5.4", {}), ("gpt-5.6-sol", {"reasoning_effort": "none"})])
def test_older_models_keep_chat_completions_with_tools(agent_context, monkeypatch, model, options):
    import litellm
    monkeypatch.setattr(agent, "MODEL", model)
    requests = []

    def complete(**kwargs):
        requests.append(deepcopy(kwargs))
        if len(requests) == 1:
            return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "old_call", "type": "function", "function": {"name": "get_hrv", "arguments": "{}"}}]}}])
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "Starszy model działa."}}])

    monkeypatch.setattr(agent.litellm, "completion", complete)
    monkeypatch.setattr(agent, "execute_tool", lambda *args: {"ok": True})
    monkeypatch.setattr(responses_api, "OpenAI", lambda **kwargs: pytest.fail("Unexpected Responses request"))
    assert agent.run_agent("test", "test") == ("Starszy model działa.", False)
    assert len(requests) == 2
    assert requests[0]["tools"] == TOOLS
    assert requests[1]["messages"][-1]["tool_call_id"] == "old_call"
    assert {key: requests[0][key] for key in options} == options
    if not options:
        assert "reasoning_effort" not in requests[0]


def test_summary_can_use_sol_with_an_older_chat_model(mock_api, monkeypatch):
    monkeypatch.setattr(summary, "SUMMARY_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("SUMMARY_MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv("SUMMARY_REASONING_EFFORT", "low")
    valid = "\n".join(label + " test" for label in summary.SUMMARY_LABELS)
    requests = mock_api([response([message("ucięty tekst")], "incomplete"), response([message(valid)])])
    assert summary._generate_summary("Testowe pliki") == (valid, "stop", 2)
    assert len(requests) == 2
    assert requests[0]["max_output_tokens"] == 4096
    assert "tools" not in requests[0]
    assert "bardzo skrótowo" in requests[1]["input"][0]["content"]


def test_summary_older_model_keeps_original_token_limit(monkeypatch):
    import litellm
    monkeypatch.setattr(summary, "SUMMARY_MODEL", "gpt-5.4")
    requests = []
    valid = "\n".join(label + " test" for label in summary.SUMMARY_LABELS)

    def complete(**kwargs):
        requests.append(kwargs)
        return litellm.ModelResponse(choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": valid}}])

    monkeypatch.setattr(summary.litellm, "completion", complete)
    monkeypatch.setattr(responses_api, "OpenAI", lambda **kwargs: pytest.fail("Unexpected Responses request"))
    assert summary._generate_summary("test") == (valid, "stop", 1)
    assert requests[0]["max_tokens"] == summary.SUMMARY_MAX_TOKENS


def test_switching_models_preserves_the_same_conversation(mock_api, agent_context, monkeypatch):
    import litellm
    legacy_requests = []

    def legacy_complete(**kwargs):
        legacy_requests.append(deepcopy(kwargs))
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "Odpowiedź starszego modelu."}}])

    monkeypatch.setattr(agent.litellm, "completion", legacy_complete)
    monkeypatch.setattr(agent, "MODEL", "gpt-5.4")
    agent.run_agent("Pierwsza wiadomość", "same-user")

    requests = mock_api([response([message("Odpowiedź Sol.")])])
    monkeypatch.setattr(agent, "MODEL", "gpt-6.1-sol")
    agent.run_agent("Druga wiadomość", "same-user")
    assert requests[0]["input"][1:3] == [
        {"role": "user", "content": "Pierwsza wiadomość"},
        {"role": "assistant", "content": "Odpowiedź starszego modelu."},
    ]

    monkeypatch.setattr(agent, "MODEL", "gpt-5.6-sol")
    agent.run_agent("Trzecia wiadomość", "same-user")
    assert legacy_requests[-1]["messages"][-2] == {"role": "assistant", "content": "Odpowiedź Sol."}
    assert len(agent.load_history("same-user")) == 6


@pytest.mark.parametrize("effort", ["none", "minimal", "typo"])
def test_unsupported_reasoning_is_rejected_before_api_call(effort):
    with pytest.raises(ValueError, match="reasoning effort"):
        responses_api.ResponsesConversation("gpt-6.1-sol", [], reasoning_effort=effort)
