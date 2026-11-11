"""Extraccion de categorias y productos del HTML de capraboacasa.com.

No normaliza: saca los campos tal como los ensena la web (precios en texto con coma, el
nombre con el tamano dentro...). El precio por unidad lo calcula el normalizador de Fission.

Cada producto del listado tiene un enlace de titulo con un JSON de analitica
(`data-metrics`) que ya trae id, nombre, marca, precio vigente y categorias:

    <a class="product-title-link" data-metrics="{...items:[{price, item_id, item_name,
       item_brand, item_category, item_category2, item_category3}]}"
       href=".../es/productdetail/972869-leche-desnatada-.../">Leche ... brik 1 litro</a>
    ...
    <p class="quantity-text"> 1 KILO A 7,69 € </p>    (precio por unidad; no siempre)
    <span class="price-offer-before"> 1,76</span>   (solo si esta en oferta)
    <span class="price-offer-now"> 1,39</span>

Cada producto sale dos veces en el HTML (vista de escritorio y movil); las copias se
fusionan quedandose con los campos que no esten vacios.
"""
import html
import json
import re

_CATEGORY = re.compile(r'href="https://[^"/]+(?::443)?(/es/supermercado/(?:[0-9]+-[^/"]+/)+)"')
_TITLE = re.compile(
    r'<a class="product-title-link" data-metrics="([^"]+)" href="([^"]+)">\s*(.*?)\s*</a>', re.S)
_BEFORE = re.compile(r'class="price-offer-before">\s*([0-9.,]+)\s*<')
_NOW = re.compile(r'class="price-offer-now">\s*([0-9.,]+)\s*<')
_UNIT = re.compile(r'class="quantity-text">\s*([^<]*?)\s*<')
_H1 = re.compile(r'<h1 class="product-lineal-title">\s*(.*?)\s*</h1>', re.S)
_PAGE = re.compile(r'[?&]pageNumber=([0-9]+)')


def leaf_categories(home_html: str, exclude: list[str]) -> list[str]:
    """Rutas de las categorias hoja (las que listan productos), sin las de `exclude`.

    Se ignoran las rutas con filtro de marca (/es/supermercado/<marca>/<cat>/...): son
    las mismas categorias filtradas."""
    paths = sorted({p for p in _CATEGORY.findall(home_html)})
    leaves = [p for p in paths if not any(q != p and q.startswith(p) for q in paths)]
    out = []
    for p in leaves:
        top = p.split("/")[3]                       # <id>-<slug> de primer nivel
        if any(x and x in top for x in exclude):
            continue
        out.append(p)
    return out


def last_page(page_html: str) -> int:
    """Ultima pagina (`?pageNumber=N`) enlazada en el paginador; 0 si solo hay una."""
    m = re.search(r'class="items pages-items">(.*?)</ul>', page_html, re.S)
    nums = [int(n) for n in _PAGE.findall(m.group(1))] if m else []
    return max(nums, default=0)


def products(page_html: str) -> list[dict]:
    """Productos de una pagina de listado, crudos."""
    h1 = _H1.search(page_html)
    category_name = html.unescape(h1.group(1)) if h1 else ""
    titles = list(_TITLE.finditer(page_html))
    out: dict[str, dict] = {}
    for k, m in enumerate(titles):
        try:
            metrics = json.loads(html.unescape(m.group(1)))
            item = (metrics.get("ecommerce") or {}).get("items", [{}])[0]
        except (ValueError, IndexError, AttributeError):
            continue
        if not item.get("item_id"):
            continue
        # Lo que hay entre este titulo y el siguiente es la ficha de este producto.
        end = titles[k + 1].start() if k + 1 < len(titles) else m.end() + 6000
        tile = page_html[m.end():end]
        before = _BEFORE.search(tile)
        now = _NOW.search(tile)
        unit = _UNIT.search(tile)
        p = {
            "platform": "caprabo",
            "id": str(item["item_id"]),
            "name": " ".join(html.unescape(m.group(3)).split()),
            "brand": item.get("item_brand", ""),
            "price": item.get("price"),                     # vigente, numerico (analitica)
            "price_now": now.group(1) if now else "",       # el que se ve, "1,39"
            "price_before": before.group(1) if before else "",  # antes de la oferta
            "unit_price_text": " ".join(html.unescape(unit.group(1)).split()) if unit else "",  # "1 KILO A 7,69 €"
            "by_weight": "Producto al peso" in tile,
            "category": category_name,
            "category_ids": [item.get(k) for k in ("item_category", "item_category2", "item_category3")
                             if item.get(k)],
            "url": m.group(2).replace(":443/", "/"),
        }
        prev = out.get(p["id"])
        if prev is None:
            out[p["id"]] = p
        else:
            for key, value in p.items():
                if value and not prev.get(key):
                    prev[key] = value
    return list(out.values())
