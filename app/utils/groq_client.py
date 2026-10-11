"""
Tiny Groq API helper (plain `requests`, no extra package needed).

Groq's API is OpenAI-compatible: POST /chat/completions with messages.
Set GROQ_API_KEY in .env. Optionally set GROQ_MODEL to override the model.
Env vars are read at call time, so .env changes work after a restart.

If a call fails, groq_chat() returns None and a SHORT readable reason is kept
in LAST_ERROR, so the bot (and `python -m app.ocr.groq_check`) can show it
instead of silently falling back to basic OCR.
"""

import json
import os
import re
import time

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Vision-capable Qwen on Groq. (qwen/qwen3.6-27b was shut down on 2026-09-14.)
DEFAULT_MODEL = "qwen/qwen3.8-27b"

LAST_ERROR = ""      # human-readable reason for the most recent failure


def groq_available():
    return bool(os.getenv("GROQ_API_KEY"))


def _models_to_try():
    """GROQ_MODEL from .env first (if set), then the known-good default, so a
    stale model name in .env can never leave the bot without a working model."""
    chosen = (os.getenv("GROQ_MODEL") or "").strip() or DEFAULT_MODEL
    return [chosen] if chosen == DEFAULT_MODEL else [chosen, DEFAULT_MODEL]


def _friendly(status, model, body):
    if status == 401:
        return "Groq rejected the API key (HTTP 401) - check GROQ_API_KEY in .env"
    if status == 403:
        return "Groq blocked the request (HTTP 403) - check the key's permissions"
    if status == 429:
        return "Groq rate limit reached (HTTP 429) - wait a minute and try again"
    if status in (400, 404):
        return f"Groq model '{model}' is not available (HTTP {status})"
    return f"Groq error (HTTP {status})"


def _post(payload, headers, timeout):
    """One request, with two safety nets:
    - 400 -> retry once without the optional settings (some models reject them)
    - 429 / 5xx -> wait a moment and retry once"""
    resp = requests.post(GROQ_URL, json=payload, headers=headers, timeout=timeout)
    if resp.status_code == 400 and ("reasoning_effort" in payload or "response_format" in payload):
        plain = {k: v for k, v in payload.items() if k not in ("reasoning_effort", "response_format")}
        resp = requests.post(GROQ_URL, json=plain, headers=headers, timeout=timeout)
    if resp.status_code in (429, 500, 502, 503, 504):
        try:
            wait = min(float(resp.headers.get("retry-after", 2)), 6)
        except (TypeError, ValueError):
            wait = 2
        time.sleep(wait)
        resp = requests.post(GROQ_URL, json=payload, headers=headers, timeout=timeout)
    return resp


def groq_chat(messages, max_tokens=4096, timeout=30, json_mode=True):
    """Send a chat request. Returns the reply text, or None on ANY failure
    (so callers can fall back to a free local method instead of crashing)."""
    global LAST_ERROR
    key = os.getenv("GROQ_API_KEY")
    if not key:
        LAST_ERROR = "GROQ_API_KEY is not set"
        return None

    headers = {"Authorization": f"Bearer {key}"}
    for model in _models_to_try():
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",    # instruct mode: faster, no "thinking" text
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = _post(payload, headers, timeout)
        except requests.Timeout:
            LAST_ERROR = f"Groq timed out after {timeout}s"
            return None
        except Exception as e:
            LAST_ERROR = f"could not reach Groq ({type(e).__name__})"
            return None

        if resp.status_code == 200:
            try:
                LAST_ERROR = ""
                return resp.json()["choices"][0]["message"]["content"]
            except Exception:
                LAST_ERROR = "Groq sent an unexpected reply format"
                return None

        LAST_ERROR = _friendly(resp.status_code, model, resp.text)
        print(f"[groq] HTTP {resp.status_code} for model {model}: {resp.text[:300]}")
        if resp.status_code not in (400, 404):
            return None      # bad key / rate limit / server error - another model won't help
    return None


def extract_json(text):
    """Pull the first JSON object out of a model reply (handles ```json fences
    and any <think>...</think> blocks). Returns a dict, or None."""
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
