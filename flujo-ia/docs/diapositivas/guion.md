# Guion · Presentación de progreso (equipo IA)

Tres slides, **~2 minutos**. Tono conversacional. Lo marcado con 🔵 es
**reserva**: no se dice en voz alta, es material por si el profesor pregunta.

> Transición desde Samuel: *"Samuel ha enseñado cómo entra y se limpia el dato;
> yo enseño cómo se responde a partir de él."*

---

## Slide 1 · Arquitectura del flujo IA (RAG) — ~30 s

"Mi parte es el motor del comparador, y este es el flujo en tres líneas.

**Arriba, el índice** — es lo que se hace una vez: las líneas limpias se
parsean a un producto por ficha, se vectorizan con embeddings y se guardan en
el índice con sus metadatos —cadena, formato, tamaño—.

**En medio, la consulta** — cada pregunta del usuario también se vectoriza,
recupera por similitud coseno con esos filtros, y entra en la cadena de
LangChain.

**Abajo, la respuesta** — el LLM redacta, los guardrails revisan citas y
cifras, y sale un JSON validado —o en streaming token a token— hacia la app.

Y el punto clave del banner: **catálogo, equivalencia y QA comparten este
mismo índice**; solo cambia la consulta y los filtros."

---

## Slide 2 · Búsqueda semántica y asistente de precios (RAG) — ~50 s

"Mi parte son tres piezas.

**Primero, la búsqueda semántica.** El usuario escribe 'aceite de oliva
barato' y no hace falta que esa palabra aparezca en el catálogo: el producto
se representa por su significado. Encima filtramos por metadatos —cadena,
formato y tamaño—.

**Segundo, la equivalencia.** Que el mismo producto de Mercadona y de
Carrefour se reconozca como el mismo. Sin esto compararíamos 1 litro contra
0,5 litros y saldrían precios falsos.

**Tercero, el asistente.** Preguntas en lenguaje natural que responde
citando los productos con su precio; si el dato no está, se abstiene en vez de
inventar.

Y el modelo lo elegimos **midiendo, no a ojo**: comparamos tres embeddings
sobre el mismo dataset y ganó e5-small, que además es el más ligero. El LLM
va en local con Ollama en la VM, con Gemini por API como alternativa."

---

## Slide 3 · Medido, no improvisado — ~45 s

"Estas cifras son medidas, no promesas.

**Equivalencia: 1,000.** Cuando solo mirábamos el primer candidato del
buscador fallaba 2 de cada 25 casos; el LLM corrige ese 8% y acierta el 100%.

**Citas inventadas: cero.** En 25 preguntas, ninguna respuesta cita un
producto que no estuviera en los datos. Eso no es suerte: hay un guardrail
que comprueba las citas y las cifras **antes** de devolver la respuesta.

**Preguntas tipo: 0,880.** El 88% trae el contenido correcto, con la cifra y
la unidad —euros por litro—. Los tres fallos: dos respuestas con la cifra
bien pero sin decir de qué cadena, y un error transitorio de Ollama.

Y los casos trampa —un pack de 2 unidades frente a 1 unidad— los descarta
**8 de 8**."

---

## 🔵 Reserva: si el profesor pregunta

### Embeddings (lo más probable 🔥)

| Pregunta | Respuesta corta |
|---|---|
| 🔥 **¿Qué es un embedding?** | Una lista de números (384) que representa el **significado** del texto. Textos parecidos quedan cerca en ese espacio, así "aceite barato" encuentra "AOVE 1 l" aunque no compartan palabras. |
| 🔥 **¿Y esas 384 dimensiones?** | Es lo que define el modelo. Suficiente para separar 257 productos; menos dimensiones = menos cálculo y menos RAM en la VM. |
| 🔥 **¿El mismo modelo para documentos y consultas?** | **Sí, obligatorio**: los dos vectores tienen que vivir en el mismo espacio o la similitud no significa nada. Y con e5 además lleva **prefijos asimétricos**: `passage: ` al indexar y `query: ` al preguntar — es lo que exige el modelo, sin ellos el recall se hunde (está en `config.py`). |
| 🔥 **¿Por qué e5-small y no algo más grande?** | Lo decidimos midiendo: mismos datos, mismos filtros, mismo código, tres modelos. **e5: 0,837 · bge-m3: 0,584** en recall@1 de catálogo. bge-m3 pesa 2,3 GB vs 471 MB, y un tercero (Qwen3-0.6B) ni siquiera cabió en la máquina (OOM). En equivalencia bge-m3 saca 1,000 —un caso más de 498—, pero en catálogo pierde 25 puntos. **El modelo pequeño gana.** |
| **¿Cómo se compara?** | `recall@k` (¿el esperado está en el top-k?) y MRR, sobre dataset con ground truth y **semilla fija**: las cifras son reproducibles por cualquier grupo. |
| **¿Cuánto tarda indexar?** | 257 productos en 27-62 s; casi todo es cargar el modelo, el embedding en sí es <1 s. |

### Búsqueda

| Pregunta | Respuesta corta |
|---|---|
| 🔥 **¿Qué es la similitud coseno?** | El **ángulo** entre los dos vectores: 1 = mismo significado, 0 = nada que ver. No depende de la longitud del texto, por eso sirve para comparar una pregunta corta con una ficha larga. |
| **¿Y los filtros?** | Cadena, formato y tamaño se aplican con los metadatos **antes** de ordenar: la similitud solo decide dentro de lo que ya cumple filtros. |
| 🔥 **¿Por qué recall@1 = 0,837 y no más alto?** | Ojo con esta: la mitad de las consultas son *"el mismo producto en las tres cadenas"* —hay **tres** respuestas válidas y acertar una no basta para que el primer resultado sea "el" correcto. Mirando `recall_full` (las tres cadenas en el top-k): **0,994 en top-3 y 1,000 en top-10**. En la práctica, casi siempre salen las tres cadenas entre los tres primeros. |

### Equivalencia, guardrails y LLM

| Pregunta | Respuesta corta |
|---|---|
| **¿Qué hace el LLM en la equivalencia?** | El buscador recupera candidatos (recall@1 **0,996**) y el LLM elige el correcto: **1,000 con LLM vs 0,920 solo retrieval** —corrige esos 2 de 25. |
| **¿Y no alucina?** | El guardrail comprueba que **cada id citado estaba en el contexto** y que las cifras aparecen en los datos; si no, avisa o se abstiene. **0 citas inventadas, 25/25.** |
| **¿Cuánto tarda?** | 9-16 s por respuesta (8B en CPU). Con el **streaming SSE** el usuario ve el primer token desde el primer segundo. |
| **¿Por qué LLM local?** | Sin claves ni cuotas. Gemini queda como alternativa con la misma interfaz: se cambia con la variable `RAG_LLM`. |
| **¿Por qué LangChain?** | Lo pide el plan. Usamos **solo LCEL** para orquestar recuperación → prompt → LLM, sobre el código que ya había; sin loaders ni piezas que no necesitamos. |
| **¿Y los datos reales?** | Ahora: sintético, **173 preguntas** de QA y **498 pares** de equivalencia, con LLM en una muestra de 25. Con datos reales estas cifras son una **cota superior**, no una predicción —y el ground truth de equivalencias habrá que etiquetar a mano. |
| **¿Qué falta?** *(la slide la quitamos)* | **pgvector** —esperando el esquema de Xavi— y **reindexar con los ficheros limpios** de Samuel. El prototipo ya está desplegado en la VM con 75 tests. |
