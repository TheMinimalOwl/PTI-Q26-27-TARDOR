# 05 · Demo: preguntas que funcionan siempre

Cuatro preguntas para la demo (tarea del plan: *"preparar 3-4 preguntas de
demo que funcionen siempre"*), elegidas sobre el dataset de prueba y
**verificadas en local** con el retrieval real (27/10, rama `ai`).

Criterio de selección: que el resultado **no dependa del humor del LLM** —
en las cuatro, el contexto recuperado ya contiene la respuesta o la ausencia
que hay que demostrar. El LLM solo redacta sobre datos que están ahí.

## Las cuatro

### 1 · Precio directo (el caso básico)

```
python -m rag.cli ask "¿Cuál es el aceite de oliva virgen extra de 1 l más barato en total?" --llm ollama
```

- **Qué demuestra:** comparación de precios con distradores (hay formatos de
  0,5 l más baratos en total, y el prompt obliga a comparar solo 1 l).
- **Respuesta esperada:** `[10002] Aceite oliva virgen extra Carrefour —
  11,70 EUR` (gold: `data/gold/qa.json`).
- **Retrieval verificado:** los tres AOVE de 1 l en el top-2 + distractores
  0,5 l en posiciones 3-4. Correcto.

### 2 · Empate por unidad (precio unitario + empates)

```
python -m rag.cli ask "¿Cuál es el aceite de oliva virgen extra de 1 l más barato por unidad?" --llm ollama
```

- **Qué demuestra:** precio unitario (EUR/l) y que el prompt obliga a decir
  *"hay empate"* cuando lo hay.
- **Respuesta esperada:** **empate de tres** a `12,50 EUR/l` — Hacendado,
  Carrefour y Alcampo (`10001`, `10002`, `10003`).
- **Retrieval verificado:** los tres empates están en el **top-3**. Correcto.

### 3 · Lookup con filtro de cadena (búsqueda simple)

```
python -m rag.cli ask "¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?" --llm ollama
```

- **Qué demuestra:** pregunta directa con la cadena como filtro; el caso
  "cuánto cuesta" que la app usará a diario.
- **Respuesta esperada:** `[10127] Agua mineral Hacendado — 0,45 EUR
  (0,30 EUR/l)`.
- **Retrieval verificado:** rank 1 = `10127` (Mercadona). Correcto.
  (Ojo: hay agua **con gas** más cara — 0,74 EUR — que sirve de distractor.)

### 4 · Fuera de catálogo (abstención, el guardrail en acción)

```
python -m rag.cli ask "¿Cuánto cuesta el arroz de 1 kg?" --llm ollama
```

- **Qué demuestra:** que **no inventa**. El arroz no existe en el catálogo
  (verificado: 0 coincidencias en `data/raw/*.txt`), y en vez de
  fabricarse un precio responde que no está.
- **Respuesta esperada:** abstención — *"No he encontrado..."* con
  `abstained: true` en el JSON.
- **Retrieval verificado:** el top-4 son manzanas, zanahorias y cebollas —
  nada que ver. El LLM no tiene de dónde sacar un precio de arroz.

## Extra · Equivalencia (pipeline aparte)

```
python -m rag.cli equiv --id 10001 --chain carrefour --llm ollama
```

Recupera los candidatos de Carrefour para el AOVE 1 l de Mercadona y el LLM
elige: el correcto es `10002` (score de recuperación 0,964), con los
distractores de 0,5 l y 0,75 l detrás. Es la pregunta que explica la frase
*"que el mismo producto se reconozca como el mismo"*.

## Cómo verificar antes de la demo

```bash
# 1. Checklist completo (entorno → tests → servicios → API → CLI)
bash scripts/verificar.sh

# 2. Las cuatro preguntas, con LLM
cd flujo-ia
for q in "¿Cuál es el aceite de oliva virgen extra de 1 l más barato en total?" \
         "¿Cuál es el aceite de oliva virgen extra de 1 l más barato por unidad?" \
         "¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?" \
         "¿Cuánto cuesta el arroz de 1 kg?"; do
  python -m rag.cli ask "$q" --llm ollama
done
```

Comprobación rápida por pregunta (lo que tiene que verse):

| # | Tiene que aparecer | Señal de alerta |
|---|---|---|
| 1 | `11.70` y `carrefour` | Responde con un precio de 0,5 l |
| 2 | `12.50` y las tres cadenas | Elige una sola cadena sin decir empate |
| 3 | `0.45` y `mercadona` | Cita el agua con gas (0,74) |
| 4 | Abstención / "no encontrado" | **Cita un precio de arroz: parar la demo** |

**Pendiente hasta que la VM vuelva:** ejecutar las cuatro con LLM
(`--llm ollama`, `qwen3:8b`) y confirmar los textos. En local solo se ha
verificado el retrieval (con `--llm none`), que es la parte que sostiene la
respuesta; el texto lo redacta el LLM en la VM.

## Por qué estas cuatro aguantan

1. **El retrieval está medido, no supuesto** — las cuatro pasadas por el
   índice local el mismo día (índice regenerado con semilla fija).
2. **Las respuestas salen del gold** (`data/gold/qa.json`), que es
   exacto: mismas cifras en cualquier máquina.
3. **Cubren los cuatro mensajes de la demo:** precio, unitario/empate,
   lookup con cadena y no-inventar.
4. **Si algo falla**, el pipeline degrada sin tumbarse: sin LLM se ve el
   retrieval, y con el guardrail ninguna cifra fuera del contexto llega
   a la pantalla.
