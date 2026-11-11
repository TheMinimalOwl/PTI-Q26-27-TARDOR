# scrapper_caprabo

Recolector de **Caprabo** (`www.capraboacasa.com`). Publica en `scraper.caprabo.raw`; el
consumer deja los lotes en `scraper.caprabo.clean` y el writer de API/BD crea la cadena sola.

## Fuente

No hay API JSON. El catálogo sale del HTML de las páginas de categoría, que el servidor
genera completo:

```
GET https://www.capraboacasa.com/es/                      → árbol de categorías (enlaces)
GET https://www.capraboacasa.com/es/supermercado/<cat1>/<cat2>/<cat3>/            → página 0
GET https://www.capraboacasa.com/es/supermercado/<cat1>/<cat2>/<cat3>/?pageNumber=1 → página 1
```

- 20 productos por página. 772 categorías hoja de supermercado (~1.150 páginas, unos 60
  minutos con 3 s de pausa); se excluyen las de primer nivel que no son de
  alimentación/droguería (`SCRAPER_EXCLUDE`: papelería, hogar, electrónica, electrohogar,
  descanso).
- Cada producto trae un JSON de analítica (`data-metrics`) con id, nombre, marca, precio
  vigente y categorías. Del HTML de la ficha se sacan además el precio anterior si está en
  oferta, la URL y, cuando la web lo enseña, el precio por unidad (`1 KILO A 2,00 €`).
- Un producto puede estar en varias categorías: se deduplica por id.

Crudo que se publica (no se normaliza nada):

```python
{"platform": "caprabo", "id": "13899893",
 "name": "Naranja de zumo PREMIER, malla 2 kg", "brand": "PREMIER",
 "price": 3.99, "price_now": "3,99", "price_before": "5,99",
 "unit_price_text": "1 KILO A 2,00 €", "by_weight": False,
 "category": "Naranjas y otros cítricos", "category_ids": ["2059698", "2059699", "2059700"],
 "url": "https://www.capraboacasa.com/es/productdetail/13899893-naranja-de-zumo-premier-malla-2-kg/"}
```

## Precio por unidad

Lo calcula el normalizador de Fission (`from_caprabo` en `fission/normalizer/normalizer.py`):

- Si la web da el precio por unidad (`1 KILO A 2,00 €`, ~78 % de los productos), manda la
  fuente (`src=fuente`).
- Si no, se calcula con el tamaño que va en el nombre: `brik 1 litro`, `pack 4x125 g`,
  `malla 2 kg`, `12 uds.`, `1/2 docena`, `rollo 30 m`, `40 lavados`; `unidad`, `pieza` y
  `manojo` sin número cuentan como 1 ud (`src=calculado`).
- En los productos al peso (`al peso, compra mínima 500 g`) el precio es el de esa cantidad
  (lo confirma la ficha: 500 g a 1,30 € = 1 kilo a 2,60 €).
- Catálogo completo (11/11/2026): 13.068 productos, 99,3 % con precio por unidad (10.162 de
  la web, 2.821 calculados) y 85 incompletos que no dicen la cantidad ("pack 1 par", "al
  corte", estuches). En una muestra, donde hay los dos, el calculado coincide con la web en
  el 98 %.

## Código postal y tienda

Sin iniciar sesión, la web enseña el catálogo de **su tienda online por defecto** (cookie
`supermarket.ali.shop`: `8284` "Caprabo_Plataforma"). El código postal solo se elige al hacer
login para pedir, así que aquí no cambia el catálogo. Caprabo reparte en Cataluña (provincias
08, 17, 25, 43): se usa el primer código postal configurado de allí; si no hay ninguno, el Job
no hace nada y acaba bien.

Se publica `wh` = id de la tienda online (`8284`) y `postal_code` = ese código postal.

## Uso responsable

Proyecto académico, sin ánimo de lucro:

- Una pasada al día a las **02:00 (hora de Madrid)**.
- Peticiones de una en una, con **`SCRAPER_DELAY` segundos** entre ellas (3 por defecto:
  unos 60 minutos). Reintentos espaciados (10 s, 20 s).
- El `robots.txt` no excluye las páginas de categoría que se usan; sí excluye las búsquedas
  (`/search/results/?q=`) y `?zipCode`, que no se usan.

## Comportamiento ante fallos

Sale con código distinto de 0 si da 0 productos, si falla más del 5 % de las categorías o si
no se pueden publicar todos. El Job tiene `activeDeadlineSeconds` de 2 h.

## Variables

| Variable | Por defecto | Efecto |
|---|---|---|
| `SCRAPER_POSTAL_CODES` | `08016` | Códigos postales, separados por comas. Más adelante los dará la API |
| `SCRAPER_DELAY` | `3` | Segundos entre peticiones |
| `SCRAPER_EXCLUDE` | `papeleria,hogar,electronica,electrohogar,descanso` | Categorías de primer nivel que no se recorren |
| `SCRAPER_MAX_CATEGORIES` | `0` (todas) | Para pruebas rápidas |
| `NATS_URL`, `NATS_STREAM`, `NATS_DRY_RUN` | | Como en los demás scrapers |

## Probar en local

```bash
cd flujo-entrada/scrappers/scrapper_caprabo
docker build -t scrapper-caprabo:dev .
docker run --rm -e NATS_DRY_RUN=1 -e SCRAPER_DELAY=2 -e SCRAPER_MAX_CATEGORIES=60 \
  -v "$PWD/out:/app/out" scrapper-caprabo:dev
```

En el clúster:

```bash
SCRAPERS=caprabo bash flujo-entrada/infra/e2e.sh
```
