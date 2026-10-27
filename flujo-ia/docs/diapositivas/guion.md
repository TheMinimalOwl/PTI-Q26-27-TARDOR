# Guion · Presentación de progreso (equipo IA)

Tres slides, **~2 minutos**. Tono conversacional; si sobra tiempo, se puede
saltar la última tarjeta de cada slide.

> Transición desde Samuel: *"Samuel ha enseñado cómo entra y se limpia el dato;
> yo enseño cómo se responde a partir de él."*

---

## Slide 5 · Búsqueda semántica y asistente de precios (RAG) — ~50 s

"Mi parte es el motor de IA del comparador: embeddings y LLM. Son tres piezas.

**Primero, la búsqueda semántica.** El usuario escribe 'aceite de oliva barato'
y no hace falta que esa palabra aparezca en el catálogo: el producto se
representa por su significado. Encima filtramos por metadatos — cadena, formato
y tamaño.

**Segundo, la equivalencia.** Que el mismo producto de Mercadona y de Carrefour
se reconozca como el mismo. Sin esto compararíamos 1 litro contra 0,5 litros y
saldrían precios falsos.

**Tercero, el asistente.** Preguntas en lenguaje natural que responde citando
los productos con su precio; si el dato no está, se abstiene en vez de inventar.

Y el modelo lo elegimos **midiendo, no a ojo**: comparamos tres embeddings sobre
un dataset con ground truth y ganó e5-small, que además es el más ligero. El
LLM va en local con Ollama en la VM, con Gemini por API como alternativa."

---

## Slide 6 · Medido, no improvisado — ~45 s

"Lo que quería destacar es que estas tres cifras son medidas, no promesas.

**Equivalencia: 1,000.** Cuando solo mirábamos el primer candidato del buscador
fallaba 2 de cada 25 casos; el LLM corrige ese 8% y acierta el 100%.

**Citas inventadas: cero.** En 25 preguntas, ninguna respuesta cita un producto
que no estuviera en los datos. Eso no es suerte: hay un guardrail que comprueba
las citas y las cifras **antes** de devolver la respuesta, y si un precio no
estaba en el contexto se avisa.

**Preguntas tipo: 0,880.** El 88% trae el contenido correcto, y siempre con la
cifra y la unidad — euros por litro. Los tres fallos restantes: dos son
respuestas con la cifra bien pero sin decir de qué cadena, y uno fue un fallo
transitorio de Ollama.

Además: los casos trampa —un pack de 2 unidades frente a 1 unidad— los descarta
los 8 de 8."

---

## Slide 7 · Estado y siguiente paso — ~30 s

"Estado: el prototipo está **desplegado en la VM del clúster**, con una API que
expone búsqueda, pregunta con streaming —token a token, para que la app pueda
pintar la respuesta en directo— y equivalencia. Arranca sola tras un reinicio.

La cadena está montada con LangChain y la salida es un JSON validado con un
esquema, que es exactamente lo que necesita la app de Fardin para consumirla.

Y lo que me falta: **pgvector**, que está esperando el esquema de base de datos
de Xavi, y **reindexar con los ficheros limpios** que va a sacar Samuel — con
datos reales, el ground truth de equivalencias habrá que etiquetar a mano."

---

## Por si preguntan

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué LLM local? | Para no depender de claves ni cuotas. Con `RAG_OLLAMA_THINK=false` la respuesta pasa de 20 s a 2 s. Gemini queda como alternativa: misma interfaz, se cambia con una variable. |
| ¿Por qué LangChain? | Lo pide el plan. Lo usamos en la orquestación (LCEL) sobre la recuperación y el LLM que ya teníamos; sin loaders ni cosas que no usamos. |
| ¿Cuánto tarda? | 9-16 s con el 8B en CPU. El streaming hace que el usuario vea algo desde el primer segundo. |
| ¿Y los datos reales? | Ahora se evalúa con datos sintéticos y ground truth exacto (173 preguntas, 498 pares). Con los reales, etiquetar equivalencias es trabajo manual. |
| ¿No se alucina? | El guardrail impide citar productos fuera del contexto y marca cifras que no están en los datos. 0 alucinaciones en la muestra. |
| ¿Dónde está? | `flujo-ia/` en la rama `ai`, 75 tests, docs de decisión de modelos, evaluación y despliegue. |
