#!/usr/bin/env python3
"""Genera las diapositivas de progreso del equipo de IA.

Toma el deck del compañero (Samuel) y le anade 3 slides de IA reutilizando su
propio diseno: se duplica el slide de las 3 tarjetas y solo se cambian los
textos, de modo que el fondo, las tarjetas, la barra de acento y el banner
quedan identicos.

    .venv/bin/python docs/diapositivas/generar_diapos.py \\
        ~/Downloads/"Presentación progreso.pptx" \\
        ~/Downloads/"Presentación progreso - IA (Joel).pptx"

Las cifras son las medidas (ver docs/03-evaluacion.md), no estimadas.

Nota sobre las coordenadas: las formas dentro de un grupo de python-pptx
devuelven coordenadas **relativas** al grupo, y como el slide tiene 3 tarjetas
en distintas posiciones, hay que resolver la posición absoluta (offset del
grupo + escala ext/chExt) antes de ordenar nada por posición.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt

# --------------------------------------------------------------------------
# Contenido de las 3 diapositivas
# (la 1 y la 3 usan el layout de "pasos", la 2 convierte las tarjetas en
# metricas con la cifra en grande)
# --------------------------------------------------------------------------

EYEBROW = "Equipo IA · Joel Forcadell"

SLIDE_1 = {
    "eyebrow": EYEBROW,
    "titulo": "Búsqueda semántica y asistente de precios (RAG)",
    "banner": (
        "Modelo elegido midiendo, no a ojo: ",
        "e5-small gana a bge-m3 en catálogo (recall@1 0,84 vs 0,58) y pesa 5× menos (471 MB).",
    ),
    "tarjetas": [
        {
            "paso": "PASO 01",
            "titulo": "Búsqueda semántica",
            "desc": (
                "Buscar productos en lenguaje natural («aceite de oliva barato») sobre el "
                "catálogo normalizado, y filtrar por cadena, formato y tamaño."
            ),
            "tags": ["e5-small", "NumPy", "Metadatos"],
        },
        {
            "paso": "PASO 02",
            "titulo": "Equivalencia",
            "desc": (
                "Encontrar el mismo producto en otra cadena para comparar precios de verdad: "
                "mismo tipo, mismo formato y mismo tamaño."
            ),
            "tags": ["Embeddings", "Ground truth", "LLM"],
        },
        {
            "paso": "PASO 03",
            "titulo": "Asistente (QA)",
            "desc": (
                "Responder preguntas citando productos con su precio, y abstenerse si el dato "
                "no está en los datos."
            ),
            "tags": ["Ollama qwen3", "Gemini", "LangChain"],
        },
    ],
}

SLIDE_2 = {
    "eyebrow": EYEBROW,
    "titulo": "Medido, no improvisado",
    "banner": (
        "Casos trampa: ",
        "8/8 descartados (un pack de 2 ud no se confunde con 1 ud). Latencia 9-16 s en la VM.",
    ),
    "tarjetas": [
        {
            "paso": "PRECISIÓN",
            "titulo": "1,000",
            "desc": (
                "de precisión@1 al elegir el equivalente en otra cadena. El retrieval solo "
                "daba 0,920: el LLM corrige ese 8%."
            ),
            "tags": ["498 pares", "3 cadenas", "muestra 25"],
        },
        {
            "paso": "CITAS",
            "titulo": "0",
            "desc": (
                "citas inventadas en 25 preguntas: todo precio citado existe en el contexto "
                "recuperado; si no, el guardrail lo quita."
            ),
            "tags": ["Guardrails", "JSON Schema", "25/25"],
        },
        {
            "paso": "PREGUNTAS",
            "titulo": "0,880",
            "desc": (
                "de contenido correcto en preguntas tipo, siempre con la cifra y la unidad "
                "(EUR/l): 22 de 25."
            ),
            "tags": ["173 preguntas", "qwen3:8b", "22/25"],
        },
    ],
    "cifra_grande": True,
}

SLIDE_3 = {
    "eyebrow": EYEBROW,
    "titulo": "Estado y siguiente paso",
    "banner": (
        "Para la app: ",
        "/ask devuelve JSON con las fuentes y /ask/stream pinta la respuesta token a token.",
    ),
    "tarjetas": [
        {
            "paso": "DESPLEGADO",
            "titulo": "VM del clúster",
            "desc": (
                "API con /search, /ask, /ask/stream y /equiv. Arranca sola tras un reinicio "
                "(systemd + Ollama local, sin claves de API)."
            ),
            "tags": ["systemd", "Ollama", "Flask"],
        },
        {
            "paso": "HECHO",
            "titulo": "Cadena con LangChain",
            "desc": (
                "Cada consulta pasa por recuperación → prompt → respuesta, con salida en JSON "
                "validado y streaming."
            ),
            "tags": ["LCEL", "SSE", "JSON Schema"],
        },
        {
            "paso": "SIGUIENTE",
            "titulo": "Datos reales",
            "desc": (
                "Reindexar con los ficheros limpios del equipo de ingesta y pgvector con el "
                "esquema de BD (bloqueado por ahí)."
            ),
            "tags": ["pgvector", "Ground truth", "Equipo ingesta"],
        },
    ],
}

# Textos del slide de plantilla (el del compañero) que hay que ir sustituyendo
TEXTO_PASO = ("PASO 01", "PASO 02", "PASO 03")
TEXTO_TITULO = ("Scrapers (K8s)", "Fission (FaaS)", "Persistencia")
TEXTO_TAGS = {
    "Python", "Playwright", "BeautifulSoup",
    "Fission Router", "Pydantic", "Python / Go",
    "PostgreSQL", "Historial Precios", "Catálogo Limpio",
}
TEXTO_EYEBROW = "Arquitectura del Sistema"
TEXTO_TITULO_SLIDE = "Flujo de Ingesta Asíncrono"
TEXTO_BANNER = "Flujo Asíncrono:"
ALTURA_DESC = (1.0, 1.6)  # pulgadas: la caja de descripción mide 1,25"


# --------------------------------------------------------------------------
# Geometría (los grupos devuelven coordenadas relativas; hay que resolverlas)
# --------------------------------------------------------------------------


def _datos_grupo(g) -> tuple[float, float, float, float, float, float]:
    """(off_x, off_y, ext_cx, ext_cy, chOff_x, chOff_y) de un grupo, en EMU."""
    xfrm = g._element.find(qn("p:grpSpPr")).find(qn("a:xfrm"))
    off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
    choff, chext = xfrm.find(qn("a:chOff")), xfrm.find(qn("a:chExt"))
    return (
        int(off.get("x")), int(off.get("y")),
        int(ext.get("cx")), int(ext.get("cy")),
        int(choff.get("x")), int(choff.get("y")),
        int(chext.get("cx")), int(chext.get("cy")),
    )


def formas_absolutas(slide) -> list[tuple[float, float, object]]:
    """Formas planas con su posición real en el slide, ordenadas por (x, y)."""
    out: list[tuple[float, float, object]] = []

    def recorrer(shapes, dx=0.0, dy=0.0, ex=1.0, ey=1.0):
        for s in shapes:
            if s.shape_type == 6:  # GROUP
                ox, oy, ccx, ccy, chx, chy, chcx, chcy = _datos_grupo(s)
                sx = ex * (ccx / chcx) if chcx else ex
                sy = ey * (ccy / chcy) if chcy else ey
                recorrer(s.shapes, dx + ox * ex, dy + oy * ey, sx, sy)
            else:
                out.append((dx + s.left * ex, dy + s.top * ey, s))

    recorrer(slide.shapes)
    out.sort(key=lambda t: (round(t[0] / 914400, 2), round(t[1] / 914400, 2)))
    return out


def clasificar_tarjetas(slide) -> list[dict]:
    """Agrupa las formas del slide de plantilla por tarjeta.

    Devuelve [{paso, titulo, desc, tags:[...]}], donde cada valor es la forma
    concreta a sustituir. Se usa la posición absoluta: cada tarjeta ocupa un
    hueco de 2,52" de ancho, de modo que el bucket de x determina la tarjeta.
    """
    formas = formas_absolutas(slide)
    buckets = [{"paso": None, "titulo": None, "desc": None, "tags": []} for _ in range(3)]

    def bucket(x_emu: float) -> int:
        x = x_emu / 914400
        return 0 if x < 3.0 else (1 if x < 5.8 else 2)

    for x, y, f in formas:
        if not f.has_text_frame:
            continue
        texto = f.text_frame.text.strip()
        alto = f.height.inches
        b = buckets[bucket(x)]
        if texto in TEXTO_PASO:
            b["paso"] = f
        elif texto in TEXTO_TITULO:
            b["titulo"] = f
        elif ALTURA_DESC[0] < alto < ALTURA_DESC[1]:
            b["desc"] = f
        elif texto in TEXTO_TAGS:
            b["tags"].append((y, x, f))  # se ordenan por fila (top, luego left)

    for b in buckets:
        b["tags"] = [f for _, _, f in sorted(b["tags"])]
    return buckets


# --------------------------------------------------------------------------
# Edición de texto
# --------------------------------------------------------------------------


def poner_texto(shape, texto: str, tam: float | None = None, negrita: bool | None = None):
    """Cambia el texto conservando el formato del primer run."""
    tf = shape.text_frame
    parrafo = tf.paragraphs[0]
    runs = parrafo.runs
    run = runs[0] if runs else parrafo.add_run()
    for extra in runs[1:]:
        extra._r.getparent().remove(extra._r)
    run.text = texto
    for p in tf.paragraphs[1:]:  # los textos largos venían partidos en párrafos
        p._p.getparent().remove(p._p)
    if tam is not None:
        run.font.size = Pt(tam)
    if negrita is not None:
        run.font.bold = negrita


def aplicar_cabecera(slide, eyebrow: str, titulo: str):
    for _, _, f in formas_absolutas(slide):
        if not f.has_text_frame:
            continue
        t = f.text_frame.text.strip()
        if t == TEXTO_EYEBROW:
            poner_texto(f, eyebrow)
        elif t == TEXTO_TITULO_SLIDE:
            poner_texto(f, titulo)


def aplicar_banner(slide, etiqueta: str, texto: str):
    """El banner inferior tiene dos runs: la etiqueta de color y la explicación."""
    for _, _, f in formas_absolutas(slide):
        if not f.has_text_frame or not f.text_frame.text.strip().startswith(TEXTO_BANNER):
            continue
        parrafo = f.text_frame.paragraphs[0]
        runs = parrafo.runs
        runs[0].text = etiqueta
        if len(runs) > 1:
            runs[1].text = texto
            for extra in runs[2:]:
                extra._r.getparent().remove(extra._r)
        else:
            nuevo = parrafo.add_run()
            nuevo.text = texto
            nuevo.font.size = Pt(8.5)
        for p in f.text_frame.paragraphs[1:]:
            p._p.getparent().remove(p._p)
        return
    raise RuntimeError("no se encontró el banner inferior")


def aplicar_tarjetas(slide, tarjetas: list[dict], cifra_grande: bool = False):
    """Sustituye el contenido de las 3 tarjetas del slide duplicado."""
    buckets = clasificar_tarjetas(slide)
    for b, t in zip(buckets, tarjetas):
        if b["paso"] is None or b["titulo"] is None or b["desc"] is None:
            raise RuntimeError(f"no se reconoció la tarjeta completa: {b}")
        poner_texto(b["paso"], t["paso"], tam=8)
        poner_texto(b["titulo"], t["titulo"], tam=24 if cifra_grande else None,
                    negrita=True if cifra_grande else None)
        poner_texto(b["desc"], t["desc"])
        if len(b["tags"]) < len(t["tags"]):
            raise RuntimeError(f"faltan huecos de tag: {len(b['tags'])} < {len(t['tags'])}")
        for forma, tag in zip(b["tags"], t["tags"]):
            poner_texto(forma, tag)


def aplicar_metricas(slide, tarjetas: list[dict]):
    """Como aplicar_tarjetas pero con la cifra en grande (slide de métricas)."""
    aplicar_tarjetas(slide, tarjetas, cifra_grande=True)


# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    origen, destino = Path(argv[1]), Path(argv[2])
    prs = Presentation(str(origen))

    plantilla = 1  # el slide de las 3 tarjetas del compañero

    # Quitar el último slide si está vacío (queda raro entre los míos). Hay que
    # borrar también la relación: si no, la parte queda huérfana y colisiona
    # al empaquetar (PowerPoint pediría reparar el archivo).
    if len(prs.slides[len(prs.slides) - 1].shapes) == 0:
        sldId = prs.slides._sldIdLst[-1]
        rid = sldId.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        prs.slides._sldIdLst.remove(sldId)
        prs.part.drop_rel(rid)

    for spec in (SLIDE_1, SLIDE_2, SLIDE_3):
        slide = duplicar_slide(prs, plantilla)
        aplicar_cabecera(slide, spec["eyebrow"], spec["titulo"])
        aplicar_tarjetas(slide, spec["tarjetas"], cifra_grande=spec.get("cifra_grande", False))
        aplicar_banner(slide, *spec["banner"])

    prs.save(str(destino))
    print(f"escrito: {destino}")
    print(f"slides totales: {len(prs.slides._sldIdLst)}")
    return 0


def duplicar_slide(prs: Presentation, indice: int):
    """Copia el slide `indice` (formas + imágenes) al final del deck."""
    origen = prs.slides[indice]
    nuevo = prs.slides.add_slide(origen.slide_layout)

    for shp in list(nuevo.shapes):  # placeholders por defecto del layout
        shp._element.getparent().remove(shp._element)

    # Las imágenes del original se re-relacionan: los rIds no se pueden reutilizar
    mapa: dict[str, str] = {}
    for rid, rel in origen.part.rels.items():
        if rel.reltype.endswith("/image"):
            parte = getattr(rel, "_target_part", None) or getattr(rel, "_target", None)
            mapa[rid] = nuevo.part.relate_to(parte, rel.reltype)

    for shp in origen.shapes:
        el = copy.deepcopy(shp._element)
        for nodo in el.iter():
            for attr in list(nodo.attrib):
                if attr.endswith("}embed") or attr.endswith("}link"):
                    destino = mapa.get(nodo.get(attr))
                    if destino:
                        nodo.set(attr, destino)
        nuevo.shapes._spTree.append(el)
    return nuevo


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
