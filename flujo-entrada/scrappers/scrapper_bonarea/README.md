# scrapper_bonarea

Recolector de **bonÀrea** (`www.bonarea-online.com`). Publica en `scraper.bonarea.raw`; el
consumer deja los lotes en `scraper.bonarea.clean` y el writer de API/BD crea la cadena sola.

## Fuente

La web no tiene API pública, pero carga los productos de cada categoría con una llamada
interna que devuelve JSON. Se encontró con **Playwright** (cargando una categoría en un
navegador y mirando qué pide); el scraper no necesita navegador:

```
GET  https://www.bonarea-online.com/categories/x/13_300_010_010_020   → cookie de sesión anónima
POST https://www.bonarea-online.com/ca/shop/ShoppingBody   reference=13*300*010*010*020
     → {"articles": [productos de la categoría], "nivells": [árbol completo de categorías], ...}
```

- Una llamada por categoría hoja devuelve **todos** sus productos (no hay paginación).
- La primera respuesta ya trae el árbol entero: 725 hojas, de las que se recorren las 345 de
  supermercado. Se excluyen las de primer nivel que no lo son (`SCRAPER_EXCLUDE`: Llar i
  jardí, Electrodomèstics, Roba..., Informàtica i papereria, Joguines i món nadó,
  Bricolatge, Automoció, Material ramader).
- Catálogo completo (11/11/2026): **6.245 productos** en 345 peticiones, unos 18 minutos con
  3 s de pausa.
- No tiene `robots.txt` (404) ni antibot.

Crudo que se publica (recortado). El scraper solo añade `category_path`, porque la respuesta
no dice en qué categoría está cada producto:

```python
{"identifier": "13*5179", "description": "Pit filetejat de gall dindi 5 u.",
 "priceToPay": 3.8, "unitPrice": "10,15 €/kg", "measurementUnit": "aprox. 374 g",
 "weightGrams": 374, "itsOnStock": True, "discount": 0,
 "urlFriendly": "https://www.bonarea-online.com/online/producte/pit-filetejat-de-gall-dindi-5-u/13_5179",
 "category_path": ["Alimentació", "Carns i ous", "Aus", "Gall dindi"], ...}
```

## Precio por unidad

Lo calcula el normalizador de Fission (`from_bonarea` en `fission/normalizer/normalizer.py`):

- `unitPrice` (`10,15 €/kg`, `33,07 €/l.`, `0,23 €/u.`, `0,10 €/d.`) en el 87 % de los
  productos: manda la fuente. Ojo: la etiqueta a veces va mal (`300,00 €/ml.` son €/l,
  `57,65 €/g.` son €/kg); el adaptador la corrige.
- Si falta, se calcula con `measurementUnit` (`70 cl.`, `pack 6 u.`, `1/2 m.`) o, si
  tampoco, con el tamaño del nombre (`... 500ml`).
- Resultado: 5.405 de la web, 352 calculados y **488 incompletos (7,8 %)**, donde la web no
  da ni precio por unidad ni tamaño (vinos, tintes, estuches). Donde hay los dos, el
  calculado coincide con la web en 5.394 de 5.397.

## Código postal y tienda

Sin iniciar sesión hay un único catálogo online: se publica `wh` = `online` y `postal_code`
= el primer código postal configurado de Cataluña; con códigos de fuera el Job no hace nada.

## Uso responsable

Proyecto académico, sin ánimo de lucro: una pasada al día a las **02:00 (hora de Madrid)**,
peticiones de una en una con **`SCRAPER_DELAY` segundos** entre ellas (3 por defecto) y
reintentos espaciados (10 s, 20 s).

## Comportamiento ante fallos

Sale con código distinto de 0 si da 0 productos, si falla más del 5 % de las categorías o si
no se pueden publicar todos. El Job tiene `activeDeadlineSeconds` de 2 h.

## Variables

| Variable | Por defecto | Efecto |
|---|---|---|
| `SCRAPER_POSTAL_CODES` | `08016` | Códigos postales, separados por comas. Más adelante los dará la API |
| `SCRAPER_DELAY` | `3` | Segundos entre peticiones |
| `SCRAPER_EXCLUDE` | (las 8 de arriba, separadas por `\|`) | Categorías de primer nivel que no se recorren |
| `SCRAPER_MAX_CATEGORIES` | `0` (todas) | Para pruebas rápidas |
| `NATS_URL`, `NATS_STREAM`, `NATS_DRY_RUN` | | Como en los demás scrapers |

## Probar en local

```bash
cd flujo-entrada/scrappers/scrapper_bonarea
docker build -t scrapper-bonarea:dev .
docker run --rm -e NATS_DRY_RUN=1 -e SCRAPER_MAX_CATEGORIES=10 -v "$PWD/out:/app/out" scrapper-bonarea:dev
```

En el clúster:

```bash
SCRAPERS=bonarea bash flujo-entrada/infra/e2e.sh
```
