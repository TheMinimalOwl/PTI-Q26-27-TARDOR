# scrapper_condis

Recolector de **Condis** (`compraonline.condis.es`). Publica en `scraper.condis.raw`; el
consumer deja los lotes en `scraper.condis.clean` y el writer de API/BD crea la cadena sola.

## Fuente

La web no sirve el catálogo ella misma: lo pide al buscador **Empathy.co**, una API JSON
pública que no necesita sesión ni tiene antibot. El scraper hace lo mismo que el navegador:

```
GET https://api.empathy.co/search/v1/query/condis/browse?browseField=store&browseValue=718&store=718&lang=es&rows=0
    → total de la tienda y sus secciones (facet facetSection)
GET https://api.empathy.co/search/v1/query/condis/browse?browseField=section&browseValue=Bebidas&store=718&lang=es&rows=500&start=0
    → productos de una sección, 500 por página
```

- La API no deja pasar de `start` 2400, así que se recorre **por secciones** (11; la mayor,
  Alimentación, tiene ~1.600). Si alguna pasara del límite, el scraper falla y avisa.
- Todo el catálogo de la tienda 718 (7.810 productos, 11/11/2026) en **~20 peticiones**,
  poco más de 1 minuto con 3 s de pausa.
- Se quita `tagging` (URLs de analítica de la web); el resto se publica tal cual.

Crudo que se publica (recortado):

```python
{"id": "116335", "description": "TORTILLAS ZANUY TRIGO 8 UNIDADES 320 G", "brand": "ZANUY",
 "price": {"current": 1.69, "regular": 1.95, "discounted": 1.69}, "pum": "5,28€/Kilo",
 "netWeight": 320, "variable_weight": 0, "on_promotion": False,
 "section": "Alimentación", "family": "Platos preparados",
 "category": ["Alimentación", "Mexicanos e internacionales", "Platos preparados"],
 "url": "/tortillas-zanuy-trigo-8-unidades-320-g/p/116335/es_ES", ...}
```

## Precio por unidad

Lo calcula el normalizador de Fission (`from_condis` en `fission/normalizer/normalizer.py`):

- La web lo da en `pum` (`5,28€/Kilo`, `0,58€/100 ml`, `3,69€/Docena`...) en el 99 % de los
  productos: manda la fuente (`src=fuente`).
- Si falta, se calcula con el tamaño del final del nombre (`... 320 G`, `... 6 UNIDADES`).
  Algunos nombres van truncados y acaban en un `0 KG` de relleno: se ignora.
- Catálogo completo (11/11/2026): 7.810 productos, 7.742 con precio por unidad de la web, 38
  calculados y 30 incompletos (0,4 %).

## Código postal y tienda

Sin iniciar sesión la web enseña la tienda **718**. La elección de tienda por código postal
la hace el servidor de la web al pedir (no hay API pública para ello), así que de momento se
usa `SCRAPER_STORE` (718). Se publica `wh` = tienda y `postal_code` = el primer código postal
configurado de Cataluña (08, 17, 25, 43); con códigos de fuera el Job no hace nada.

## Uso responsable

Proyecto académico, sin ánimo de lucro: una pasada al día a las **02:00 (hora de Madrid)**,
~20 peticiones de una en una con **`SCRAPER_DELAY` segundos** entre ellas (3 por defecto) y
reintentos espaciados (10 s, 20 s).

## Comportamiento ante fallos

Sale con código distinto de 0 si da 0 productos, si falta más de un 2 % respecto al total que
da la API o si no se pueden publicar todos.

## Variables

| Variable | Por defecto | Efecto |
|---|---|---|
| `SCRAPER_POSTAL_CODES` | `08016` | Códigos postales, separados por comas. Más adelante los dará la API |
| `SCRAPER_STORE` | `718` | Tienda de Condis |
| `SCRAPER_DELAY` | `3` | Segundos entre peticiones |
| `NATS_URL`, `NATS_STREAM`, `NATS_DRY_RUN` | | Como en los demás scrapers |

## Probar en local

```bash
cd flujo-entrada/scrappers/scrapper_condis
docker build -t scrapper-condis:dev .
docker run --rm -e NATS_DRY_RUN=1 -v "$PWD/out:/app/out" scrapper-condis:dev
```

En el clúster:

```bash
SCRAPERS=condis bash flujo-entrada/infra/e2e.sh
```
