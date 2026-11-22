def collect_raw(category_json: dict) -> list[dict]:
    """Productos de una subcategoria. Tolera listas a null (la API las devuelve a veces)."""
    items = []
    for sub in category_json.get("categories") or []:
        if not isinstance(sub, dict):
            continue
        for p in sub.get("products") or []:
            if isinstance(p, dict):
                items.append(p)
    return items
