"""Clientes de LLM: hibrido local (Ollama) / API (Gemini) / sin LLM.

Por que hibrido y no solo uno:
- **Ollama (local)** es el modo por defecto porque no necesita claves, no cuesta
  dinero y la demo funciona sin red. Es un modelo pequeno (4B), asi que el
  prompt tiene que ser cerrado y la respuesta corta.
- **Gemini (API)** da mas calidad con la cuenta de la universidad (mas cuota
  que el tier gratuito) y es la opcion a comparar en la evaluacion.
- **none** deja el pipeline en modo solo-recuperacion. Sirve para medir la
  calidad del retrieval (que es lo que decide el modelo de embeddings) sin
  depender de ninguna API.

Ambos clientes exponen la misma interfaz (`chat`), de forma que el pipeline no
sabe (ni le importa) quien responde.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import requests

from . import config


class LLMError(RuntimeError):
    """Fallo al llamar al LLM (red, credenciales, modelo que no existe...)."""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_s: float = 0.0
    tokens: int | None = None
    raw: dict = field(default_factory=dict)


class BaseLLM:
    """Interfaz comun."""

    provider = "base"
    model = "-"

    def chat(self, system: str, user: str) -> LLMResponse:  # pragma: no cover - interfaz
        raise NotImplementedError

    def describe(self) -> dict:
        return {"provider": self.provider, "model": self.model}


class NoLLM(BaseLLM):
    """Modo sin LLM: responde siempre que no hay LLM configurado."""

    provider = "none"
    model = "-"

    def chat(self, system: str, user: str) -> LLMResponse:
        raise LLMError(
            "No hay LLM configurado (RAG_LLM=none). El pipeline funciona en "
            "modo solo-recuperacion."
        )


class OllamaLLM(BaseLLM):
    """LLM local con Ollama (http://localhost:11434 por defecto)."""

    provider = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None, timeout: float | None = None):
        self.model = model or config.OLLAMA_MODEL
        self.host = (host or config.OLLAMA_HOST).rstrip("/")
        self.timeout = timeout or config.OLLAMA_TIMEOUT

    def chat(self, system: str, user: str) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": config.TEMPERATURE,
                "num_ctx": 4096,
            },
        }
        url = f"{self.host}/api/chat"
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise LLMError(f"Ollama no responde en {url}: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"Ollama {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        text = (data.get("message") or {}).get("content", "")
        return LLMResponse(
            text=text,
            provider=self.provider,
            model=self.model,
            tokens=data.get("eval_count"),
            raw={"done": data.get("done"), "total_duration": data.get("total_duration")},
        )


class GeminiLLM(BaseLLM):
    """LLM remoto con la API de Gemini (AI Studio).

    La clave se lee de `GEMINI_API_KEY` o `GOOGLE_API_KEY`. Con la cuenta
    universitaria hay mas cuota que en el tier gratuito.
    """

    provider = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None, timeout: float | None = None):
        self.model = model or config.GEMINI_MODEL
        self.api_key = api_key or config.gemini_api_key()
        self.timeout = timeout or config.GEMINI_TIMEOUT
        if not self.api_key:
            raise LLMError(
                "Falta GEMINI_API_KEY (o GOOGLE_API_KEY). "
                "La clave se saca de https://aistudio.google.com/apikey"
            )

    def _endpoint(self) -> str:
        return f"{config.GEMINI_API_BASE}/models/{self.model}:generateContent"

    def chat(self, system: str, user: str) -> LLMResponse:
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": config.TEMPERATURE,
                "maxOutputTokens": 1024,
            },
        }
        # Los modelos 2.5 razonan por defecto y eso cuesta tokens y latencia
        # para un prototipo. Se puede desactivar; si el modelo lo rechaza
        # (modelo 3.x) se reintenta sin el bloque.
        thinking_budget = _thinking_budget()
        if thinking_budget is not None:
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": thinking_budget}

        resp = self._post(body)
        if resp.status_code == 400 and "thinkingConfig" in resp.text:
            body["generationConfig"].pop("thinkingConfig", None)
            resp = self._post(body)
        if resp.status_code != 200:
            raise LLMError(f"Gemini {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text,
            provider=self.provider,
            model=self.model,
            tokens=usage.get("totalTokenCount"),
            raw={"finishReason": (data.get("candidates") or [{}])[0].get("finishReason")},
        )

    def _post(self, body: dict) -> requests.Response:
        try:
            return requests.post(
                self._endpoint(),
                json=body,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise LLMError(f"Gemini no responde: {e}") from e


def _thinking_budget() -> int | None:
    """Presupuesto de razonamiento: `RAG_GEMINI_THINKING` (0 = sin razonar)."""
    import os

    raw = os.environ.get("RAG_GEMINI_THINKING")
    if raw is None:
        return 0
    try:
        return int(raw)
    except ValueError:
        return None


def build_llm(provider: str | None = None, model: str | None = None) -> BaseLLM:
    """Construye el cliente segun el proveedor (`ollama` | `gemini` | `none`)."""
    provider = (provider or config.DEFAULT_LLM).lower()
    if provider in ("none", "off", "sin-llm"):
        return NoLLM()
    if provider == "ollama":
        return OllamaLLM(model=model)
    if provider == "gemini":
        return GeminiLLM(model=model)
    raise LLMError(f"Proveedor de LLM desconocido: {provider!r} (usa {config.LLM_PROVIDERS})")


# ---------------------------------------------------------------------------
# Utilidades de respuesta
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def extract_json(text: str) -> dict | list | None:
    """Saca un JSON de la respuesta del LLM, aunque venga con vallas o texto.

    Los modelos pequenos se inventan comillas y commentary; esto es
    deliberadamente tolerante porque si el JSON falla se pierde el item, no
    el lote entero.
    """
    if not text:
        return None
    blob = text.strip()
    m = _FENCE_RE.search(blob)
    if m:
        blob = m.group(1).strip()
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        pass
    # Busca el primer objeto o array balanceado del texto.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = blob.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(blob)):
            ch = blob[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(blob[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None
