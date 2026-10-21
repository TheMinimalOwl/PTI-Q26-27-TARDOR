"""Guardrails del asistente: lo que se comprueba **antes** de responder.

Un guardrail es una comprobacion automatica sobre la respuesta. No sustituye
al LLM: es la red de seguridad, y su salida viaja en la respuesta (campo
`guardrails`) para que la app pueda avisar al usuario.

Los tres controles que aplican a este dominio:

1. **Citas validas**: todo identificador `[id]` que cita la respuesta tiene que
   estar en el contexto recuperado. Si no, el modelo se ha inventado un
   producto (o se ha equivocado de formato).
2. **Cifras del contexto**: todo numero con decimales que aparece en la
   respuesta tiene que existir en el contexto. Es la forma de cazar un precio
   inventado, que es el fallo mas grave en un comparador de precios.
3. **Abstencion**: si el contexto esta vacio, no hay respuesta; y si el modelo
   dice que no encuentra el dato, la abstention es una respuesta **valida**
   (no un fallo).

En modo estricto (el de por defecto) la respuesta se corrige: se quitan las
citas invalidas y se marcan las cifras que no estan en el contexto, de forma
que la app nunca muestra un precio que no viene de los datos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .store import Hit

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMA_RESPUESTA = SCHEMA_DIR / "respuesta-asistente.schema.json"

# Numero "con decimales" (2 o mas) o con thousand separators: 12.50, 0,767, 1.234,56
_NUMERO_PRECIO = re.compile(r"\d+(?:[.,]\d{2,})")
# Identificador citados entre corchetes
_CITA = re.compile(r"\[([^\[\]]+)\]")
# Frases con las que el modelo se abstiene
_ABSTENCION = re.compile(
    r"no (?:he )?(?:encontrado|hay|consta|aparece)|no tengo|sin datos|no puedo|"
    r"no se encuentra|ningun producto|no aparece",
    re.IGNORECASE,
)


@dataclass
class ResultadoGuardrails:
    """Resultado de aplicar los controles a una respuesta."""

    ok: bool = True
    advertencias: list[str] = field(default_factory=list)
    citas_inventadas: list[str] = field(default_factory=list)
    cifras_fuera_del_contexto: list[str] = field(default_factory=list)
    citas_validas: bool = True
    cifras_validas: bool = True
    abstention: bool = False
    respuesta_corregida: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "warnings": list(self.advertencias),
            "citations_valid": self.citas_validas,
            "numbers_valid": self.cifras_validas,
        }


def _numeros(texto: str) -> list[str]:
    return _NUMERO_PRECIO.findall(texto or "")


def _contexto_numeros(hits: list[Hit]) -> set[str]:
    """Todos los numeros que aparecen en el contexto recuperado."""
    numeros: set[str] = set()
    for h in hits:
        d = h.doc
        for campo in ("total", "unit_price", "size"):
            valor = d.get(campo)
            if valor is None:
                continue
            try:
                dec = Decimal(str(valor))
            except Exception:
                continue
            numeros.add(f"{dec:.4f}".rstrip("0").rstrip("."))
            numeros.add(f"{dec:.2f}")
            numeros.add(f"{dec:.3f}")
            numeros.add(f"{dec:.4f}")
    return numeros


def _coincide(numero: str, numeros: set[str]) -> bool:
    """El numero de la respuesta esta en el contexto (con tolerancia de redondeo)."""
    limpio = numero.replace(" ", "")
    try:
        valor = Decimal(limpio.replace(",", "."))
    except Exception:
        return True  # si no es un numero, no es una cifra
    for ref in numeros:
        try:
            base = Decimal(ref)
        except Exception:
            continue
        if abs(valor - base) <= Decimal("0.011"):
            return True
    return False


def aplicar_guardrails(
    respuesta: str,
    hits: list[Hit],
    estricto: bool = True,
    citas_esperadas: list[str] | None = None,
) -> ResultadoGuardrails:
    """Comprueba y (en modo estricto) corrige la respuesta."""
    resultado = ResultadoGuardrails(respuesta_corregida=respuesta or "")
    texto = respuesta or ""

    # -- 0. Abstension: es una respuesta valida ----------------------------
    if not hits:
        resultado.abstention = True
        resultado.advertencias.append("No hay productos en el contexto: la respuesta es una abstención.")
        resultado.ok = False
        if estricto:
            resultado.respuesta_corregida = (
                "No he encontrado productos que respondan a la pregunta."
            )
        return resultado

    if _ABSTENCION.search(texto):
        resultado.abstention = True

    # -- 1. Citas ----------------------------------------------------------
    ids_contexto = {str(h.doc.get("id")) for h in hits}
    citadas = _CITA.findall(texto)
    invalidas = sorted({c for c in citadas if c.strip() not in ids_contexto})
    resultado.citas_inventadas = invalidas
    resultado.citas_validas = not invalidas
    if invalidas:
        resultado.ok = False
        resultado.advertencias.append(
            f"El modelo cita productos que no estan en el contexto: {', '.join(invalidas)}."
        )
        if estricto:
            for inválida in invalidas:
                texto = texto.replace(f"[{inválida}]", "[?]")

    # -- 2. Cifras ---------------------------------------------------------
    numeros = _contexto_numeros(hits)
    fuera = [n for n in _numeros(texto) if not _coincide(n, numeros)]
    resultado.cifras_fuera_del_contexto = fuera
    resultado.cifras_validas = not fuera
    if fuera:
        resultado.ok = False
        resultado.advertencias.append(
            f"La respuesta contiene cifras que no estan en el contexto: {', '.join(fuera)}."
        )

    # -- 3. Citas esperadas (opcional) ------------------------------------
    if citas_esperadas:
        sin_cubrir = [c for c in citas_esperadas if c not in citadas]
        if sin_cubrir:
            resultado.advertencias.append(
                "La respuesta no cita alguno de los productos esperados: "
                + ", ".join(sin_cubrir)
            )

    resultado.respuesta_corregida = texto.strip()
    return resultado


# ---------------------------------------------------------------------------
# Construccion de la respuesta y validacion con JSON Schema
# ---------------------------------------------------------------------------


def construir_respuesta(
    question: str,
    respuesta: str | None,
    hits: list[Hit],
    fuentes: list[str] | None = None,
    confianza: float = 0.0,
    abstained: bool = False,
    guardrails: ResultadoGuardrails | None = None,
    provider: str = "none",
    model: str | None = None,
    latencia_s: float = 0.0,
    motivos: dict[str, str] | None = None,
) -> dict:
    """Monta el dict que sale por `/ask`, con la forma del JSON Schema."""
    ids_fuente = [str(s) for s in (fuentes or [])]
    por_id = {str(h.doc.get("id")): h.doc for h in hits}
    motivos = motivos or {}

    sources = []
    for id_ in ids_fuente:
        d = por_id.get(id_)
        if d is None:
            continue
        sources.append(
            {
                "id": str(d.get("id")),
                "name": str(d.get("name", "")),
                "chain": str(d.get("chain", "")),
                "price_total": _float(d.get("total")),
                "price_unit": _float(d.get("unit_price")),
                "unit": d.get("unit") or None,
                "url": d.get("url") or None,
                "reason": motivos.get(id_, ""),
            }
        )

    g = guardrails or ResultadoGuardrails()
    return {
        "question": question,
        "answer": respuesta or "",
        "sources": sources,
        "confidence": max(0.0, min(1.0, float(confianza))),
        "abstained": bool(abstained),
        "guardrails": g.as_dict(),
        "provider": provider,
        "model": model,
        "latency_s": round(float(latencia_s), 3),
    }


def _float(valor) -> float | None:
    if valor is None:
        return None
    try:
        return float(str(valor))
    except (TypeError, ValueError):
        return None


def validar(respuesta: dict) -> list[str]:
    """Valida la respuesta contra el JSON Schema. Devuelve los errores (vacio = ok)."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError:  # pragma: no cover - jsonschema es dependencia declarada
        return []
    schema = json.loads(SCHEMA_RESPUESTA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in e.path) or 'raiz'}: {e.message}"
        for e in sorted(validator.iter_errors(respuesta), key=lambda e: list(e.path))
    ]
