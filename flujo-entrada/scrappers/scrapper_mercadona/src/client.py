import requests

TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0"}
CHANGE_PC_URL = "https://tienda.mercadona.es/api/postal-codes/actions/change-pc/"


def fetch_json(url: str, params: dict | None = None) -> tuple[int | None, dict]:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return r.status_code, {}
        return r.status_code, r.json()
    except requests.RequestException:
        return None, {}


def resolve_wh(postal_code: str) -> str | None:
    """Almacen de Mercadona que sirve `postal_code` (p. ej. 08016 -> bcn1), o None.

    Es lo que hace la web al escribir el codigo postal: la respuesta trae el almacen en la
    cabecera `x-customer-wh`. Despues el catalogo se pide con `?wh=<almacen>`.
    """
    try:
        r = requests.put(CHANGE_PC_URL, json={"new_postal_code": postal_code},
                         headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return r.headers.get("x-customer-wh") or None
