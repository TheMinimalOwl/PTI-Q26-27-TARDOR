def collect_raw(category_json: dict) -> list[dict]:
    items = []
    for sub in category_json.get("categories", []):
        for p in sub.get("products", []):
            items.append(p)
    return items
