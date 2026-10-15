def normalize_item(p: dict) -> str:
    pid = str(p.get("id", "-"))
    nombre = " ".join(str(p.get("display_name", "")).split())
    pi = p.get("price_instructions") or {}
    total = pi.get("unit_price", "-")
    ref = pi.get("reference_price", "-")
    ref_fmt = pi.get("reference_format", "")
    size = pi.get("unit_size", "-")
    size_fmt = pi.get("size_format", "")
    url = p.get("share_url", "")
    cats = p.get("categories") or []
    cat = cats[0].get("name", "") if cats else ""
    return f"{pid} | {nombre} | {total}EUR total | {ref}EUR/{ref_fmt} | {size}{size_fmt} | {cat} | {url}"


def to_clean_txt(items: list[dict]) -> str:
    lines = [f"Items: {len(items)}", "---"]
    for p in items:
        if "_errors" in p:
            continue
        try:
            lines.append(normalize_item(p))
        except Exception as e:
            lines.append(f"ERROR id={p.get('id', '?')}: {e}")
    return "\n".join(lines) + "\n"


def _unwrap(data) -> list[dict]:
    items = data if isinstance(data, list) else data.get("items", [data])
    out = []
    for it in items:
        out.append(it.get("product", it) if isinstance(it, dict) else it)
    return out


def main():
    from flask import request, Response
    import json

    raw = request.get_data(cache=False)
    try:
        data = json.loads(raw or b"null")
    except Exception:
        return Response("Body debe ser JSON: dict producto, envelope {product:...} o {\"items\": [...]}", status=400, mimetype="text/plain")
    return Response(to_clean_txt(_unwrap(data)), mimetype="text/plain")
