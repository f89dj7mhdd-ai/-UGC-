"""LLMクライアント（Ollama / Anthropic / OpenAI 自動検出）.

優先順位:
  1. 環境変数 LLM_PROVIDER があればそれを使用（"ollama" / "anthropic" / "openai"）
  2. ANTHROPIC_API_KEY → anthropic
  3. OPENAI_API_KEY → openai
  4. ローカルの Ollama が起動していれば ollama（キー不要・既定の推奨）
いずれも無ければ is_available()=False を返し、呼び出し側はキーワード/辞書へフォールバック。

追加依存を避け標準ライブラリ(urllib)のみ。失敗時は None を返す（例外を伝播しない）。
"""
from __future__ import annotations

import json
import os
import urllib.request

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"

_ollama_cache: bool | None = None


def _ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _ollama_reachable() -> bool:
    global _ollama_cache
    if _ollama_cache is not None:
        return _ollama_cache
    try:
        req = urllib.request.Request(f"{_ollama_host()}/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as r:  # noqa: S310
            _ollama_cache = r.status == 200
    except Exception:
        _ollama_cache = False
    return _ollama_cache


def _provider() -> str | None:
    p = os.environ.get("LLM_PROVIDER")
    if p:
        return p.lower()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if _ollama_reachable():
        return "ollama"
    return None


def is_available() -> bool:
    return _provider() is not None


def provider_name() -> str:
    return _provider() or "none"


def _post(url: str, headers: dict, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str | None:
    """LLMにプロンプトを投げ、テキスト応答を返す。失敗・未設定時は None。"""
    prov = _provider()
    try:
        if prov == "ollama":
            model = os.environ.get("OLLAMA_MODEL", os.environ.get("LLM_MODEL", "llama3.1"))
            msgs = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
            resp = _post(f"{_ollama_host()}/api/chat", {"content-type": "application/json"},
                         {"model": model, "messages": msgs, "stream": False}, timeout=120)
            return resp.get("message", {}).get("content") or None
        if prov == "anthropic":
            model = os.environ.get("LLM_MODEL", "claude-3-5-haiku-latest")
            body = {"model": model, "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}]}
            if system:
                body["system"] = system
            resp = _post(_ANTHROPIC_URL, {
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01", "content-type": "application/json",
            }, body)
            return "".join(p.get("text", "") for p in resp.get("content", [])) or None
        if prov == "openai":
            model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
            msgs = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
            resp = _post(_OPENAI_URL, {
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "content-type": "application/json",
            }, {"model": model, "messages": msgs, "max_tokens": max_tokens})
            return resp["choices"][0]["message"]["content"] or None
    except Exception:
        return None
    return None


def complete_json(prompt: str, system: str = "", max_tokens: int = 1024):
    """LLM応答からJSONを抽出して返す。失敗時は None。"""
    text = complete(prompt, system=system, max_tokens=max_tokens)
    if not text:
        return None
    return _extract_json(text)


def _extract_json(text: str):
    """テキスト中のJSONオブジェクト/配列を抽出してパース。

    最も外側（先に現れる方）の opener を優先する。オブジェクト内に配列が
    入れ子になっていても、外側のオブジェクト全体を取り出せるようにする。
    """
    candidates = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidates.append((start, text[start:end + 1]))
    for _, frag in sorted(candidates):  # 先に現れる opener を優先
        try:
            return json.loads(frag)
        except json.JSONDecodeError:
            continue
    return None
