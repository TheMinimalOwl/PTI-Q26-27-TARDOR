# 06 · Integración con la API y la app

Contrato para que el **equipo de API/BD** y la **app** consuman el RAG sin
leer el código. Es el soporte de la tarea del plan *"Integración final con
API y app. Pruebas con la app real"* (17-18/11).

## Como arrancar el servicio

```bash
cd flujo-ia
python -m rag.serve --host 0.0.0.0 --port 8080   # indice ya indexado
# comprobacion
curl -s http://localhost:8080/health
curl -s http://localhost:8080/docs               # documentacion HTML
```

Variables que interesan a la integracion (el resto en `rag/config.py`):

| Variable | Default | Para que sirve |
|---|---|---|
| `RAG_LLM` | `ollama` | `ollama` / `gemini` / `none` (sin LLM: solo retrieval) |
| `RAG_OLLAMA_MODEL` | `qwen3:4b` | modelo (en la VM: `qwen3:8b`) |
| `RAG_OLLAMA_THINK` | — | `false` acelera mucho la respuesta (20 s → 2 s) |
| `RAG_PORT` | `8080` | puerto del servicio |

## CORS

El servicio responde con `Access-Control-Allow-Origin: *` en **todas** las
rutas (incluido el preflight `OPTIONS`), asi que la app puede llamarlo desde
cualquier origen en el navegador. No hay que tocar nada en el proxy.

## Endpoints

### `GET /health`

```json
{"ok": true, "n_productos": 257,
 "embeddings": {"key": "e5-small", "dim": 384},
 "llm": {"provider": "ollama", "model": "qwen3:8b"}, "llm_error": null}
```

Sirve para el arranque de la app: si `ok` es `false`, el indice no esta
cargado; si `llm` es `null`, el asistente solo devolvera retrieval.

### `POST /search` — busqueda de catalogo

```json
{"query": "aceite de oliva", "k": 5,
 "chain": "mercadona", "min_total": null, "max_total": 10}
```

Filtros disponibles ademas de `chain`: `chains` (lista), `category`,
`min_total`, `max_total`, `min_unit_price`, `max_unit_price`. Todos
opcionales. Devuelve `resultados` (con `rank`, `score`, `id`, `name`,
`chain`, `total`, `unit_price`, `unit`, `size`, `url`) y, si hay LLM,
`respuesta` redactada.

### `POST /equiv` — equivalencia entre cadenas

```json
{"id": "10001", "chain": "carrefour"}     // o {"nombre": "aceite de oliva"}
```

Devuelve `origen`, `candidatos` (top-k en la cadena destino), `elegido`
(el equivalente o `null`), `confianza` y `motivo`. **404** si el producto
origen no existe.

### `POST /ask` — el asistente (el que consume la pantalla de preguntas)

```json
{"question": "¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?", "k": 8}
```

Devuelve **JSON validado contra el esquema**
[`rag/schemas/respuesta-asistente.schema.json`](../rag/schemas/respuesta-asistente.schema.json):

```json
{
  "question": "¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?",
  "answer": "El agua mineral de 1.5 l en Mercadona cuesta 0.45 EUR (0.30 EUR/l) [10127].",
  "sources": [{"id": "10127", "name": "Agua mineral Hacendado", "chain": "mercadona",
               "price_total": 0.45, "price_unit": 0.30, "unit": "l",
               "url": "https://tienda.mercadona.es/product/10127", "reason": "..."}],
  "confidence": 0.8,
  "abstained": false,
  "guardrails": {"ok": true, "warnings": [], "citations_valid": true, "numbers_valid": true},
  "provider": "ollama", "model": "qwen3:8b", "latency_s": 9.4
}
```

Que debe mirar la app:

| Campo | Uso en la app |
|---|---|
| `answer` | Texto a pintar. Puede contener citas `[id]` — si quieres, resalta el `id` contra `sources` |
| `sources` | Fichas de producto (precio, cadena, url) para pintar debajo |
| `abstained` | `true` → pintar el aviso "no encontrado", **no** un error |
| `guardrails.ok` | `false` → hay `warnings`; opcionalmente muestra el aviso |
| `confidence` | 0.8 normal · 0.3 abstencion · 0.0 hubo problemas |
| `latency_s` | Solo informativo |

Cuerpo extra opcional: `"estricto": false` desactiva la correccion de
citas (por defecto `true`: las citas invalidas se sustituyen por `[?]`).

### `POST /ask/stream` — respuesta token a token (SSE)

Mismo cuerpo que `/ask`. Respuesta `text/event-stream` con tres eventos:

```
event: fuentes
data: ["10127", "10129"]

event: token
data: "El agua"

event: fin
data: {"question": "...", "respuesta": "...", "hits": [...]}
```

Consumo minimo desde JS:

```js
const r = await fetch("/ask/stream", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({question}),
});
const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
// leer trozos, separar por "\n\n", parsear "event:" y "data:"
```

**Si no hay LLM** (`RAG_LLM=none`) contesta **400** con
`{"error": "streaming necesita un LLM configurado..."}` — la app debe
caer a `/ask` en ese caso.

## Errores

| Codigo | Cuando |
|---|---|
| `400` | Falta `query`/`question`; o `/ask/stream` sin LLM |
| `404` | `/equiv`: no existe el producto origen |
| `500` | Inesperado: el cuerpo es `{"error": "..."}`. `/ask/stream` no falla asi: el error viaja como `event: error` |

No hay autenticacion: el servicio es para la red interna del proyecto.

## Plan de pruebas (17-18/11)

1. **Smoke con curl** (en la VM):

   ```bash
   curl -s localhost:8080/health | head -c 300
   curl -s -X POST localhost:8080/ask -H 'Content-Type: application/json' \
     -d '{"question":"¿Cuál es el aceite de oliva virgen extra de 1 l más barato en total?"}'
   ```

2. **Las 4 preguntas de demo** con el checklist de [`05-demo.md`](05-demo.md).
3. **Desde la app real**: una pregunta de las 4 + pintado de `sources` +
   caso `abstained` (el arroz) + streaming si la app lo usa.
4. **Fallos**: sin LLM (`/ask/stream` → 400), pregunta vacía (400),
   producto inexistente en `/equiv` (404).
5. **Reinicio**: parar y arrancar el servicio; `/health` vuelve a `ok: true`
   (la unidad systemd arranca solo).

Criterio de aceptacion: la app pinta respuesta + fichas sin parsear nada a
mano (todo sale del JSON del contrato) y ninguna cifra fuera del contexto
llega a la pantalla.

## Limitaciones conocidas para la integracion

- **Latencia 9-16 s** por respuesta con el 8B en CPU: para la app, usar
  `/ask/stream` (el usuario ve texto desde el primer segundo).
- **Indice estatico**: se regenera con `python -m rag.cli index`. Si el
  equipo de API monta recarga automatica, el aviso es al recargar el
  servicio, no en caliente.
- **Sin paginacion**: `k` maximo razonable 20; `/search` devuelve todo lo
  pedido de una.
- **Dataset de prueba**: con los ficheros reales cambian los productos, no
  el contrato.
