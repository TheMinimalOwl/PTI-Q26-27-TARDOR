# scrapper_consum

Recolector del catálogo completo de **Consum** (`tienda.consum.es`). Publica cada producto
crudo en NATS (`scraper.consum.raw`) y deja un volcado de depuración en
`out/consum_<tienda>_<fecha>.txt`. No normaliza nada: eso lo hace el normalizador de Fission.

## Fuente

Es la misma API JSON que usa la web de la tienda. No hace falta sesión ni cookies. El
código postal decide qué tienda reparte y, con ello, el surtido:

```
GET https://tienda.consum.es/api/rest/V1.0/shipping/area?shippingMethod=D,X,T,L&zipCode=08016
→ [{ "shippingAreas": [{ "shippingZoneId": "378D", "deliveryTypeId": "D",
                         "zone": { "id": 378, "storeCode": "378", "name": "Centro 378", ... } }] }]

GET https://tienda.consum.es/api/rest/V1.0/catalog/product?limit=100&offset=N
    X-TOL-ZONE: 378
    X-TOL-SHIPPING-ZONE: 378D
→ { "totalCount": 8611, "hasMore": true, "products": [ ... ] }
```

Es lo mismo que hace la web al escribir el código postal (se ve en su JavaScript: el
servicio de envío guarda la zona y la manda en esas cabeceras). Sin cabeceras, la API usa
una zona por defecto.

`limit=100` es el máximo que acepta, así que el catálogo de una tienda son unas 90 páginas.

Campos que usa el normalizador (el resto viaja crudo y se ignora):

| Campo | Ejemplo | Para qué |
|---|---|---|
| `code` | `"1669"` | Id público del producto (el de la URL). `id` es interno |
| `productData.name` | `"Rabanito Bolsa"` | Nombre |
| `productData.description` | `"Rabanito Bolsa 250 Gr"` | Tamaño (del final del texto) |
| `productData.url` | `https://tienda.consum.es/es/p/rabanito-bolsa/1669` | URL |
| `priceData.prices[]` | `PRICE` y, si hay oferta, `OFFER_PRICE` | `centAmount` = precio en euros (pese al nombre); `centUnitAmount` = precio por unidad |
| `priceData.unitPriceUnitType` | `1 Kg`, `1 L`, `1 U`, `100 ml`, `100 Gr`, `1 Lv`, `1 Dc`, `1 M`, `1 Do` | Unidad del precio por unidad |
| `categories[0].name` | `"Zanahorias y otras raíces"` | Categoría |
| `ean` | `"8423230065137"` | No entra todavía en la línea limpia (ver `docs/05-pendientes.md`) |

La traducción a la forma común está en `fission/normalizer/normalizer.py` (`from_consum`) y
el detalle en [`docs/03-contratos-datos.md`](../../docs/03-contratos-datos.md#mapeo-de-campos-de-consum).

## Uso responsable

Es un proyecto académico, sin ánimo de lucro, y los datos no se usan para ningún beneficio.
Aun así:

- Una sola pasada al día, a las **02:00 (hora de Madrid)**, con el CronJob.
- Peticiones de una en una, con **`SCRAPER_DELAY` segundos entre páginas** (5 por defecto:
  unos 8 minutos por pasada).
- Si una página falla, reintenta 3 veces esperando 10 s y 20 s; si sigue fallando, para.
- El `robots.txt` de Consum excluye `/api/` (igual que el de Mercadona excluye todo menos
  `/product`). Lo dejamos dicho en la memoria y mantenemos la carga al mínimo.

## Comportamiento ante fallos

Igual que el de Mercadona (desde el 11/11), **sale con código distinto de 0** si no ha conseguido ningún
producto o si no ha podido publicarlos todos. Así el Job queda como fallido en Kubernetes en
vez de terminar "bien" sin datos.

## Limitaciones conocidas

- **Paginación por `offset`:** si el catálogo cambia durante la pasada, algunos productos
  se desplazan de página. Se deduplica por `id`, pero se pueden perder unos pocos (sin zona
  se perdieron 9.354 de 9.427; con la zona de 08016 salieron los 8.611 de 8.611).
- **Tienda:** se publica con `wh` = código de la tienda que reparte en cada código postal
  (`378` para 08016) y `postal_code`. Si Consum no reparte en un código postal (Madrid,
  Sevilla), se salta con un aviso.
- **Precio por zona:** en las pruebas cambia el surtido entre zonas, pero no el precio de un
  mismo producto (288 productos comparados entre Barcelona, Valencia y la zona por defecto).
- **Productos a peso** (fruta, carnicería): `centAmount` es el precio aproximado de la pieza;
  lo comparable es el precio por kg, que siempre viene de la fuente.

## Variables

| Variable | Por defecto | Efecto |
|---|---|---|
| `SCRAPER_DELAY` | `5` | Segundos entre páginas |
| `SCRAPER_LIMIT` | `100` | Productos por página |
| `SCRAPER_POSTAL_CODES` | `08016` | Códigos postales, separados por comas. Más adelante los dará la API |
| `NATS_URL` | `nats://nats.messaging.svc.cluster.local:4222` | Servidor NATS |
| `NATS_SUBJECT` | `scraper.consum.raw` | Subject de publicación |
| `NATS_DRY_RUN` | `0` | `1` = no publica (solo volcado txt) |
| `USER_AGENT` | `Mozilla/5.0 (compatible; academic-price-research)` | Cabecera `User-Agent` |

## Probar en local

```bash
cd flujo-entrada/scrappers/scrapper_consum
docker build -t scrapper-consum:dev .
docker run --rm -e NATS_DRY_RUN=1 -e SCRAPER_DELAY=2 -v "$PWD/out:/app/out" scrapper-consum:dev
```

En el clúster:

```bash
CHAINS=consum bash flujo-entrada/infra/e2e.sh
```
