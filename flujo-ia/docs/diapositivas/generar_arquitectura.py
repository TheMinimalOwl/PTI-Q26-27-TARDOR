#!/usr/bin/env python3
"""Genera el diagrama de arquitectura del flujo IA (RAG).

SVG con el mismo diseno que el deck del equipo (fondo slate #0F172A, acentos
verde/azul/indice, Arial). Salida: SVG (editable) + PNG 1920x1080 (16:9, para
pegarlo en Google Slides).

    .venv/bin/python docs/diapositivas/generar_arquitectura.py
    google-chrome --headless --screenshot=... (ver mas abajo)

El PNG lo hace Chrome headless si esta instalado; si no, ImageMagick.
"""

from __future__ import annotations

from pathlib import Path

AQUI = Path(__file__).resolve().parent
SVG = AQUI / "arquitectura-ia.svg"
PNG = AQUI / "arquitectura-ia.png"

# Paleta del deck
FONDO = "#0F172A"
TARJETA = "#1E293B"
TEXTO = "#F8FAFC"
TENUE = "#94A3B8"
TENUE2 = "#64748B"
VERDE = "#34D399"
AZUL = "#38BDF8"
INDIGO = "#818CF8"
FUENTE = "Arial, Helvetica, sans-serif"

W, H = 1920, 1080
MARGEN = 110
CAJA_W, CAJA_H = 388, 150
CAJA_X = [110, 548, 986, 1424]  # 4 columnas, hueco de 50 px
FILA_Y = [300, 540, 780]

FILAS = [
    {
        "color": VERDE,
        "etiqueta": "ÍNDICE · una vez por cadena",
        "cajas": [
            ("Líneas limpias", "salida del normalizador", "equipo de ingesta"),
            ("Parser", "1 chunk = 1 producto", "campos + metadatos"),
            ("Embeddings", "e5-small · 384 d", "local, 471 MB"),
            ("Índice vectorial", "coseno + filtros", "NumPy hoy · pgvector luego"),
        ],
    },
    {
        "color": AZUL,
        "etiqueta": "CONSULTA · cada petición",
        "cajas": [
            ("App / API", "pregunta en lenguaje natural", "POST /ask"),
            ("Embeddings", "la consulta → vector", "mismo modelo, misma escala"),
            ("Recuperación", "coseno + filtros", "cadena · formato · tamaño"),
            ("Cadena LangChain", "prompt + contexto", "LCEL sobre langchain-core"),
        ],
    },
    {
        "color": INDIGO,
        "etiqueta": "RESPUESTA · salida al usuario",
        "cajas": [
            ("LLM", "Ollama qwen3 · Gemini", "mismo cliente, RAG_LLM"),
            ("Guardrails", "citas · cifras · abstención", "0 alucinaciones en la muestra"),
            ("JSON Schema", "respuesta validada", "answer + sources + confidence"),
            ("App", "JSON o streaming SSE", "eventos: fuentes · token · fin"),
        ],
    },
]


def escapar(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def caja(x: float, y: float, color: str, titulo: str, sub1: str, sub2: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="{CAJA_W}" height="{CAJA_H}" rx="14"
        fill="{TARJETA}" stroke="{color}" stroke-width="2.5"/>
  <text x="{x + 22}" y="{y + 52}" font-family="{FUENTE}" font-size="30" font-weight="bold"
        fill="{TEXTO}">{escapar(titulo)}</text>
  <text x="{x + 22}" y="{y + 94}" font-family="{FUENTE}" font-size="23" fill="{TENUE}">{escapar(sub1)}</text>
  <text x="{x + 22}" y="{y + 126}" font-family="{FUENTE}" font-size="21" fill="{TENUE2}">{escapar(sub2)}</text>"""


def flecha_h(x1: float, x2: float, y: float, color: str, mid: str) -> str:
    """Flecha horizontal de x1 a x2 en la y dada."""
    return (f'\n  <line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" '
            f'stroke-width="3" marker-end="url(#{mid})"/>')


def main() -> int:
    # marcadores de punta de flecha (uno por color)
    marcadores = "".join(
        f'<marker id="p-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>'
        for c in (VERDE, AZUL, INDIGO)
    )

    piezas: list[str] = []
    piezas.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">\n<defs>{marcadores}</defs>'
        f'\n<rect width="{W}" height="{H}" fill="{FONDO}"/>'
    )

    # Cabecera (igual que las diapositivas)
    piezas.append(f"""
  <text x="{MARGEN}" y="92" font-family="{FUENTE}" font-size="26" fill="{AZUL}"
        letter-spacing="1">Equipo IA</text>
  <text x="{MARGEN}" y="152" font-family="{FUENTE}" font-size="54" fill="{TEXTO}">Arquitectura del flujo IA (RAG)</text>
  <rect x="{MARGEN}" y="214" width="150" height="8" rx="4" fill="{AZUL}"/>""")

    # Filas (etiqueta + cajas + flechas horizontales)
    for indice_fila, (fila, y) in enumerate(zip(FILAS, FILA_Y)):
        color = fila["color"]
        # La etiqueta de la última fila sube: el codo de conexión pasa justo
        # debajo de ella y si se queda en su sitio, la línea la cruza.
        dy_etiqueta = 46 if indice_fila == 2 else 16
        piezas.append(
            f'\n  <text x="{MARGEN}" y="{y - dy_etiqueta}" font-family="{FUENTE}" font-size="24" '
            f'font-weight="bold" letter-spacing="1.5" fill="{color}">{escapar(fila["etiqueta"])}</text>'
        )
        for i, (t1, t2, t3) in enumerate(fila["cajas"]):
            x = CAJA_X[i]
            piezas.append(caja(x, y, color, t1, t2, t3))
            if i < 3:
                piezas.append(flecha_h(x + CAJA_W + 6, CAJA_X[i + 1] - 10, y + CAJA_H / 2,
                                       color, f"p-{color[1:]}"))

    # Conexión índice → recuperación (sale de la caja 4 de la fila 1 y baja
    # hasta la caja 3 de la fila 2). Etiqueta: lo que circula.
    cx1 = CAJA_X[3] + CAJA_W / 2
    cx3 = CAJA_X[2] + CAJA_W / 2
    y1_fin = FILA_Y[0] + CAJA_H
    y_codo = 495
    piezas.append(
        f'\n  <path d="M {cx1} {y1_fin} V {y_codo} H {cx3} V {FILA_Y[1] - 8}" fill="none" '
        f'stroke="{VERDE}" stroke-width="3" marker-end="url(#p-{VERDE[1:]})"/>'
        f'\n  <text x="{cx3 + 24}" y="{y_codo - 12}" font-family="{FUENTE}" font-size="22" '
        f'fill="{VERDE}">vectores + metadatos del índice</text>'
    )

    # Conexión del final de la fila 2 al principio de la fila 3 (codo). Baja
    # pegada a las cajas y gira por encima de ellas, por debajo de la etiqueta
    # de la fila (si no, la línea cruza el texto).
    cx4 = CAJA_X[3] + CAJA_W / 2
    cx_in = CAJA_X[0] + CAJA_W / 2
    y2_fin = FILA_Y[1] + CAJA_H
    y_codo2 = FILA_Y[2] - 30
    piezas.append(
        f'\n  <path d="M {cx4} {y2_fin} V {y_codo2} H {cx_in} V {FILA_Y[2] - 8}" fill="none" '
        f'stroke="{INDIGO}" stroke-width="3" marker-end="url(#p-{INDIGO[1:]})"/>'
    )

    # Banner inferior (como el del compañero)
    piezas.append(f"""
  <rect x="{MARGEN}" y="975" width="{W - 2 * MARGEN}" height="64" rx="12" fill="{TARJETA}"/>
  <text x="{MARGEN + 30}" y="1016" font-family="{FUENTE}" font-size="25">
    <tspan fill="{AZUL}" font-weight="bold">Tres pipelines — catálogo, equivalencia, QA — </tspan>
    <tspan fill="{TENUE}">comparten el mismo índice: solo cambia la consulta y los filtros.</tspan>
  </text>""")

    piezas.append("\n</svg>")
    svg = "".join(piezas)
    SVG.write_text(svg, encoding="utf-8")
    print(f"SVG: {SVG}")

    # PNG: Chrome headless (mejor rasterizado de fuentes); si no, ImageMagick.
    # Chrome renderiza un SVG suelto con margenes por defecto y deja la parte
    # inferior sin pintar; para que el viewport sea exacto, se embebe el SVG
    # en un HTML sin margen y con overflow oculto.
    import shutil
    import subprocess

    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if chrome:
        html = (AQUI / "arquitectura-ia.render.html")
        html.write_text(
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<style>html,body{margin:0;padding:0;overflow:hidden;background:%s}</style>"
            "</head><body>%s</body></html>" % (FONDO, svg),
            encoding="utf-8",
        )
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             f"--screenshot={PNG}", f"--window-size={W},{H + 120}",
             "--force-device-scale-factor=1", html.as_uri()],
            check=True, capture_output=True, timeout=180,
        )
        # Chrome solo pinta el viewport (ventana − ~90 px) y el resto sale en
        # blanco: se renderiza con margen de sobra y se recorta al 16:9 exacto.
        subprocess.run(
            ["convert", str(PNG), "-crop", f"{W}x{H}+0+0", "+repage", str(PNG)],
            check=True, timeout=60,
        )
        html.unlink()  # temporal de render, no se versiona
        print(f"PNG (chrome): {PNG}")
    else:
        subprocess.run(["convert", "-background", FONDO, str(SVG), str(PNG)], check=True)
        print(f"PNG (imagemagick): {PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
