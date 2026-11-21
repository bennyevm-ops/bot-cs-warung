import json

import httpx
import pytest

from bot_cs_warung.llm import LLMClient, is_grounded

CONTEXT = (
    "Daftar harga:\n- Indomie Goreng: Rp3.500\nJam buka: 06.00 - 21.00\nParkir: di depan warung"
)


def client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMClient("https://llm.example/v1/", "sk-test", "model-x", http=http)


def completion(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_from_env_needs_all_three_settings():
    full = {"LLM_API_BASE": "https://llm.example/v1", "LLM_API_KEY": "k", "LLM_MODEL": "m"}
    assert LLMClient.from_env(full) is not None
    assert LLMClient.from_env({}) is None
    for missing in full:
        assert LLMClient.from_env({**full, missing: ""}) is None


def test_ask_sends_question_with_shop_knowledge():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return completion("Bisa kak, parkir di depan warung.")

    assert client(handler).ask("bisa parkir?", CONTEXT) == "Bisa kak, parkir di depan warung."
    assert seen["url"] == "https://llm.example/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "model-x"
    system, user = seen["body"]["messages"]
    assert CONTEXT in system["content"] and "HANDOFF" in system["content"]
    assert user == {"role": "user", "content": "bisa parkir?"}


@pytest.mark.parametrize("content", ["HANDOFF", "handoff.", "", None])
def test_ask_returns_none_when_model_does_not_know(content):
    assert client(lambda r: completion(content)).ask("bisa hutang?", CONTEXT) is None


def test_ask_rejects_invented_price():
    reply = "Rokok Surya Rp25.000 kak."
    assert client(lambda r: completion(reply)).ask("harga rokok surya?", CONTEXT) is None


def test_ask_allows_price_from_knowledge():
    reply = "Indomie Goreng Rp3.500 kak."
    assert client(lambda r: completion(reply)).ask("mie goreng berapa?", CONTEXT) == reply


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, text="boom"),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"choices": []}),
    ],
)
def test_ask_returns_none_on_api_failure(handler):
    assert client(handler).ask("bisa parkir?", CONTEXT) is None


def test_ask_returns_none_on_network_error():
    def handler(request):
        raise httpx.ConnectError("down")

    assert client(handler).ask("bisa parkir?", CONTEXT) is None


@pytest.mark.parametrize(
    ("answer", "grounded"),
    [
        ("Indomie Goreng Rp3.500 kak.", True),
        ("Indomie Goreng 3500 kak.", True),
        ("Buka jam 06.00 sampai 21.00.", True),
        ("Bisa kak, 2 motor muat.", True),
        ("Indomie Goreng Rp4.000 kak.", False),
        ("Biayanya 10rb kak.", False),
        ("Sekitar 1,5jt kak.", False),
        ("Permen Rp500 kak.", False),
        ("Cuma 0,5rb kak.", False),
        ("Permen 500 aja kak.", False),
    ],
)
def test_is_grounded(answer, grounded):
    assert is_grounded(answer, CONTEXT) is grounded


def test_is_grounded_accepts_amounts_from_the_question():
    assert is_grounded("Untuk 600rb, ketik: transfer 600rb", CONTEXT, "kalau 600rb gimana?")
