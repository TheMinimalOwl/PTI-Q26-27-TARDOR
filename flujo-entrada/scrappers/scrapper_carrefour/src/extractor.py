from bs4 import BeautifulSoup

# Selectores candidatos, sin normalizar. Se prueba en orden.
SELECTORS = [
    "[data-test='product-card']",
    ".product-card",
    ".ebx-result__item",
    ".product-item",
    "div[class*='product']",
]

def extract_raw(html: str, base_url: str) -> list[dict]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    for sel in SELECTORS:
        cards = soup.select(sel)
        if len(cards) >= 2:
            items = []
            for c in cards[:20]:
                text = " ".join(c.get_text(separator=" ", strip=True).split())
                link = c.select_one("a[href]")
                href = link["href"] if link and link.has_attr("href") else ""
                if href.startswith("/"):
                    href = "https://www.carrefour.es" + href
                items.append({"texto_raw": text[:300], "url_raw": href})
            return items
    # Fallback: sin tarjetas detectadas, devuelve vacio
    return []
