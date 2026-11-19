import json
import ssl

import httpx
import pytest

from base.Base import Base
from module.Config import Config
from module.Engine.API import IndexTranslate
from module.Engine.API.ModelList import list_models
from module.Engine.TaskRequester import TaskRequester
from module.PromptBuilder import PromptBuilder
from module.Secret.SecretStore import MemoryBackend, SecretStore


MODEL = "Index-Translate-35B-A3B"
FORMAT = Base.APIFormat.INDEX_TRANSLATE


@pytest.fixture(autouse=True)
def isolate_clients_and_credentials(monkeypatch):
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    TaskRequester.reset()
    yield
    TaskRequester.reset()


@pytest.mark.parametrize("keys, expected_auth", [([], None), (["test-key"], "Bearer test-key")])
def test_index_translate_streaming_request(monkeypatch, keys, expected_auth):
    config = Config()
    platform = {
        "api_format": FORMAT,
        "api_url": IndexTranslate.API_URL,
        "model": MODEL,
        "api_key": keys,
        "thinking": {"level": "HIGH"},
    }
    srcs = ["Hello, [player]!", "Goodbye."]
    messages, _ = PromptBuilder(config).generate_prompt(srcs, [], [], False)
    reply = '{"translations":[{"request_index":0,"text":"你好，[player]！"},{"request_index":1,"text":"再见。"}]}'

    def handle(request):
        assert str(request.url) == f"{IndexTranslate.API_URL}/chat/completions"
        assert request.headers["user-agent"] == IndexTranslate.USER_AGENT
        assert request.headers.get("authorization") == expected_auth
        assert json.loads(request.content) == {
            "model": MODEL,
            "messages": messages,
            "max_tokens": TaskRequester.resolve_output_token_limit(config, platform),
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": False},
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        chunk = {"choices": [{"index": 0, "delta": {"content": reply}}]}
        usage = {"choices": [], "usage": {"prompt_tokens": 52, "completion_tokens": 22}}
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=(
            f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(usage)}\n\ndata: [DONE]\n\n"
        ))

    def make_client(proxy_url, timeout, *, verify):
        assert verify.verify_mode == ssl.CERT_REQUIRED
        return httpx.Client(transport=httpx.MockTransport(handle), timeout=timeout)

    monkeypatch.setattr("module.Engine.TaskRequester.create_httpx_client", make_client)
    result = TaskRequester(config, platform, 0).request(messages, response_shape="json_object")
    assert result == (False, "", reply, 52, 22)


def test_index_translate_models_can_be_loaded_without_auth(monkeypatch):
    def handle(request):
        assert str(request.url) == f"{IndexTranslate.API_URL}/models"
        assert request.headers["user-agent"] == IndexTranslate.USER_AGENT
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"data": [{"id": MODEL}, {"id": "Index-Translate-9B"}]})

    monkeypatch.setattr(
        "module.Engine.API.ModelList.create_httpx_client",
        lambda *args, **kwargs: httpx.Client(transport=httpx.MockTransport(handle)),
    )
    assert list_models(IndexTranslate.API_URL, "", FORMAT) == [MODEL, "Index-Translate-9B"]
