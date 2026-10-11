"""Groq client: every HTTP call is mocked."""
from unittest.mock import patch, MagicMock

from app.utils import groq_client as gc


def resp(status, text="ok"):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = {"choices": [{"message": {"content": text}}], "error": {"message": "bad"}}
    r.text = "err"
    return r


MSG = [{"role": "user", "content": "hi"}]


def test_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert gc.groq_chat(MSG) is None


def test_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with patch("app.utils.groq_client.requests.post", return_value=resp(200, "hello")):
        assert gc.groq_chat(MSG) == "hello"


def test_unauthorised_gives_none_and_reason(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with patch("app.utils.groq_client.requests.post", return_value=resp(401)):
        assert gc.groq_chat(MSG) is None
    assert gc.LAST_ERROR


def test_rate_limit_retries_once(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with patch("app.utils.groq_client.requests.post", side_effect=[resp(429), resp(200, "fine")]), \
         patch("app.utils.groq_client.time.sleep"):
        assert gc.groq_chat(MSG) == "fine"


def test_timeout_returns_none(monkeypatch):
    import requests
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with patch("app.utils.groq_client.requests.post", side_effect=requests.Timeout()):
        assert gc.groq_chat(MSG) is None


def test_stale_model_never_strands_default(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.6-27b")
    assert gc._models_to_try() == ["qwen/qwen3.6-27b", gc.DEFAULT_MODEL]
    monkeypatch.delenv("GROQ_MODEL")
    assert gc._models_to_try() == [gc.DEFAULT_MODEL]
