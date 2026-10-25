# SuperAhorro · Decisiones de diseño y guía de estilos

Oct 20, 2026 · @FardinA143

## Resumen

SuperAhorro compara el precio de la compra supermercados de Barcelona y te dice dónde sale más barata tu lista. 
Este documento recoge las decisiones de diseño tomadas y las reglas de estilo que deben seguir la app y la web.

- Diseño y prototipo: [Figma · Comparador de precios · pantallas](https://www.figma.com/design/ef4Nqke990mR4qQkD97Rub)
- Páginas del archivo: 00 Fundamentos, 01 Componentes, 02 App móvil (claro, oscuro, Android y Material 3) y 03 Web (1440 y 390, claro y oscuro).
- Tokens exportados: `superahorro-tokens.json` en la carpeta del proyecto.

## Principios de diseño


1. **Un dato principal por pantalla** Cada pantalla contesta una pregunta (dónde es más barato, cuánto ahorro, por dónde voy) y esa respuesta se ve sin hacer scroll.
2. **Filas, no tarjetas.** Listas con separador fino; las tarjetas solo agrupan un resumen.
3. **Familia de fuentes Source.** Source Serif 4 para titulares; todo lo demás en Source Sans 3.
4. **Un diseño, tres plataformas.** Mismos tokens y componentes; cambian las convenciones de cada sistema.

## Decisiones de producto y navegación

Todas se tomaron el 20 de octubre de 2026 durante la revisión del diseño.

| Decisión | Motivo |
| --- | --- |
| Navegación de 4 pestañas: Inicio, Buscar, Lista y Cuenta | De esta forma respondemos a las preguntas principales: Cúanto, dónde y el qué, y finalmente la pantalla de la cuenta y configuraciones |
| La Ruta es un recorrido por las tiendas de tu lista | Responde a «por dónde voy para pagar menos y ahorrarme tiempo» (el tiempo es dinero) |
| Las cestas incompletas van en un grupo aparte, «Les falta algo», con «4 de 5» como dato principal | Un total sin todos los productos no es comparable y parecía el más barato |
| Las ofertas llevan etiqueta propia y precio efectivo, pero «Más barato» compara el precio de una unidad | Una oferta tipo «2.ª unidad al 70 %» obliga a comprar dos |
| Inicio se titula «Hoy en Gràcia» en vez de «Inicio» | Personalizamos la experiencia al usuario |
| Con 1 unidad, el botón «−» del selector de cantidad pasa a papelera | Deja claro que el siguiente toque borra el producto |
| Modo oscuro elegible en Cuenta › Apariencia (Automática, Claro, Oscuro) y con el botón luna/sol en la web | El usuario decide; Automática sigue al sistema |

## Datos y contenido

La ciudad de referencia es Barcelona (Gràcia y l’Eixample) y las cadenas son 8, siempre en este orden fijo: Alcampo, Consum, Carrefour, Caprabo, Dia, Ametller Origen, Lidl y Mercadona. 

Cesta de ejemplo (5 productos: aceite Carbonell 1 l, leche Pascual 6 × 1 l, pechuga de pollo 500 g, arroz SOS 1 kg y huevos L):

| Cadena | Total | Productos | Tienda de referencia |
| --- | --- | --- | --- |
| Alcampo | 19,38 € | 5 de 5 | c/ de Sardenya 350 · 650 m |
| Consum | 19,57 € | 5 de 5 | c/ de Verdi 52 · 1,2 km |
| Carrefour | 19,95 € | 5 de 5 | Travessera de Gràcia 151 · 2,1 km |
| Caprabo | 20,59 € | 5 de 5 | c/ Gran de Gràcia · 300 m |
| Dia | 16,34 € | 4 de 5 | c/ del Torrent de l’Olla · 400 m |
| Ametller Origen | 14,48 € | 4 de 5 | c/ de Bonavista · 500 m |
| Lidl | 6,70 € | 2 de 5 | c/ de Còrsega 320 · 1,4 km |
| Mercadona | 6,60 € | 2 de 5 | c/ de Sant Salvador 30 · 900 m |

Repartida en Consum, Mercadona, Carrefour y Alcampo, la cesta cuesta 18,90 € (0,48 € menos). Si se cambia un precio, hay que actualizar totales, diferencias, «x de 5» y subtotales de la ruta en todas las pantallas.

**Tono de los textos**

- Frases cortas, en segunda persona: «Tu lista sale más barata en Alcampo».
- Cifras con coma decimal y € detrás con espacio: 3,97 €, 3,97 €/l.
- Los nombres de cadena se escriben normal (Alcampo, Mercadona), nunca imitando el logotipo.
- Siempre se indica la fuente: «Precios leídos hoy a las 8:15 en la web de cada cadena».

## Color y tokens

Ningún color se pinta a mano: todo va a una variable de la colección `SA · Color`, que tiene modo Light y Dark. En código cada token es `var(--sa-<grupo>-<nombre>)`.

Paleta base (21 oct 2026, elegida en Color Hunt): **#D9D28B** amarillo, **#B2BD7E** oliva claro, **#8E9162** oliva grisáceo, **#6A795D** verde salvia. Sustituye al ámbar anterior.

| Token | Claro | Oscuro | Uso |
| --- | --- | --- | --- |
| fondo/base | #F6F4E8 | #141611 | Fondo de pantalla |
| fondo/superficie | #FDFCF7 | #1C1F18 | Tarjetas de resumen, menú web |
| fondo/superficie-2 | #EDEBDA | #252920 | Buscador, barras inferiores |
| fondo/superficie-3 | #E3E1C9 | #2F3428 | Miniatura de producto |
| borde/hairline | #DEDBC4 | #363B2E | Separadores de fila |
| texto/principal | #1E2219 | #ECEADB | Texto y nombres de cadena |
| texto/secundario | #5A5F4E | #B3B4A0 | Datos secundarios, cestas incompletas |
| texto/titulo | #2F3A27 | #F2EFD8 | Títulos en serif |
| accion/primaria | #6A795D | #B2BD7E | Botón principal |
| accion/sobre-primaria | #FFFFFF | #1E2419 | Texto sobre botón principal |
| accion/enlace | #4E5B43 | #D9D28B | Enlaces, pestaña activa |
| accion/icono | #6A795D | #B2BD7E | Iconos activos (solo gráficos) |
| estado/tinte | #EFEBC4 | #D9D28B al 14 % | Fila del mejor precio, etiqueta de oferta |
| estado/sobre-tinte | #3A4130 | #E6E0A6 | Texto sobre tinte |
| estado/bajada | #4E6B3A | #A9C78F | Precio que baja |
| estado/subida | #9A4A2E | #E39A80 | Precio que sube, borrar |

Los colores marca/\* están atenuados (saturación al 55 %) para que convivan con la paleta oliva; siguen siendo solo un punto de 8 px.

**Color de marca de las cadenas**

- Los tokens `marca/*` (alcampo, consum, carrefour, caprabo, dia, ametller, lidl, mercadona) solo pintan un punto de 8 px junto al nombre.
- Nunca se usan como color de texto: Alcampo, Dia y Caprabo son tres rojos casi iguales y varios no llegan a 4,5:1.
- En el mapa de la Ruta, el número de parada identifica la tienda; el color es solo apoyo.

Espaciado (`SA · Espaciado`): escala de 4, 8, 12, 16, 20, 24, 32, 40, 48 y 64 px. Margen lateral de 16 px en móvil y columna de 1200 px en la web. Radios: 10 px (`radio/10`) y píldora (`radio/completo`).

## Tipografía

Dos familias, cada una con un papel fijo. **Source Serif 4** solo en títulos de pantalla; **Source Sans 3** en todo lo demás. 

| Estilo | Familia y peso | Tamaño / interlineado | Uso |
| --- | --- | --- | --- |
| Display/34 | Source Serif 4 Medium | 34 / 40 | Título grande de pantalla (Inicio, Lista) |
| Título/22 | Source Serif 4 Medium | 22 / 28 | Título de sección y de pantalla secundaria |
| Titular/17 | Source Sans 3 Semibold | 17 / 22 | Nombre de producto, cabecera de fila |
| Cuerpo/17 | Source Sans 3 Regular | 17 / 24 | Texto principal |
| Cuerpo/15 · Cuerpo/15 Medio | Source Sans 3 Regular / Medium | 15 / 20 | Filas de lista, descripciones |
| Pie/13 · Pie/13 Medio | Source Sans 3 Regular / Medium | 13 / 18 | Fuente del dato, fecha, metadatos |
| Etiqueta/11 | Source Sans 3 Semibold, mayúsculas | 11 / 14 | Etiquetas de sección en móvil |
| Precio/34 · /22 · /17 · /15 | Source Sans 3 Semibold, cifras tabulares | 34 · 22 · 17 · 15 | Precios y totales |
| Botón/17 · Botón/15 | Source Sans 3 Semibold | 17 · 15 | Botones |
| Nota/11 | Source Sans 3 Regular | 11 / 14 | Notas internas de Fundamentos, no se usa en pantallas |

Reglas:

- La serif nunca baja de 22 px ni aparece en botones, precios o filas.
- Todos los precios usan cifras tabulares para que las columnas se alineen.
- En web de escritorio el texto mínimo es 13 px; los 11 px solo se permiten en móvil para etiquetas.
- Jerarquía por tamaño y peso, no por color: el color secundario se reserva para metadatos.

## Espaciado, radios y componentes

Todo se construye con instancias de la página **01 Componentes** y colores ligados a las variables de SA · Color. Escala de espaciado 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64; margen lateral 16 en móvil; radio 10 para superficies y píldora completa para botones y chips.

| Componente | Variantes y propiedades | Reglas |
| --- | --- | --- |
| Cadena | Tono = Principal / Secundario | Punto de 8 px en color marca/\* y nombre en texto neutro. El color de marca nunca va en el texto. |
| Fila de precio | Estado = Mejor / Normal / No disponible; Oferta (booleano); Texto oferta | Filas. «Más barato» compara el precio de una unidad; la oferta se muestra como chip y no cambia el orden. |
| Selector de cantidad | Unidades = 1 / Varias | Con 1 unidad el botón de restar es una papelera. |
| Barra de pestañas | 4 pestañas: Inicio, Buscar, Lista, Cuenta | Se responde a una cuestión por pantalla |
| Botón | Principal / Secundario / Texto | Un solo botón principal por pantalla. |
| Chip | Normal / Seleccionado | Filtros y oferta. |
| Campo de búsqueda | Vacío / Con texto | En instancias, no sobrescribir el relleno con variables: copiar el del componente principal. |
| Control segmentado | 2 o 3 opciones | Cambio de vista. |
| Selector de apariencia | Sistema / Claro / Oscuro | En G3 Apariencia. |

Grupo «Les falta algo»: las cadenas con la cesta incompleta van debajo, separadas, mostrando «x de 5» en lugar del total. En la tabla web el total se sustituye por «—» y «Faltan N».

## Plataformas

**iOS (base).** Marcos de 390 × 844. Es el diseño de referencia de la app React Native.

**Android.** Marcos de 412 × 915 con barra de estado y barra de gestos de Android. El archivo tiene dos opciones:

- El mismo diseño de estilo iOS comprobado a 412 de ancho, con el panel de ajustes (G1–G3).
- Una versión completa en **Material 3** (secciones «App · Material 3 (Android)» y su gemela oscura): flecha atrás con título a la izquierda, barra de navegación con indicador en píldora, botones y búsqueda en píldora, chips con esquinas de 8 px, botones segmentados con borde, hojas inferiores con esquinas de 28 px, interruptores y radios M3. Usa los mismos tokens de color y las mismas fuentes.

**Web 1440.** Marcos de 900 de alto con scroll vertical y menú fijo arriba. Columna de contenido de 1200 px. Botón Tema que alterna claro y oscuro. Navegación con un único enlace «Mi lista · 5»; la búsqueda del menú se oculta en W1 porque la portada ya tiene la suya. La tabla de comparación sigue el orden fijo de cadenas.

**Web 390.** Versión móvil de la web en claro y oscuro, con la misma estructura que la app.

## Modo oscuro, accesibilidad y contraste

El modo oscuro no es una inversión: cada pantalla tiene su gemela con el modo Dark de SA · Color aplicado de forma explícita. Al cambiar una pantalla clara hay que volver a clonar su gemela y rehacer los enlaces del prototipo.

| Par | Contraste | Veredicto |
| --- | --- | --- |
| Colores marca/\* como texto | Por debajo de 4,5:1 en varios casos | No se usan como texto, solo como punto de 8 px |
| accion/enlace sobre fondo | 6,6:1 | Cumple AA |
| texto/secundario sobre fondo | 6,0:1 | Cumple AA |
| Texto blanco sobre botón verde salvia | 4,7:1 | Cumple AA |
| Texto sobre botón oliva claro (oscuro) | 7,9:1 | Cumple AA |
| Iconos #6A795D sobre fondo | 4,2:1 | Cumple para elementos gráficos |

Reglas:

- En oscuro, estado/tinte es #D9D28B al 14 % de opacidad, no un color sólido.
- Ningún estado se comunica solo con color: «Más barato» y «No disponible» llevan texto y la oferta lleva chip.
- Texto mínimo de 13 px en escritorio; zonas táctiles de al menos 44 × 44 (48 en Material 3).
- Comprobar el contraste en los dos modos cada vez que se añade un token.

## Movimiento e interacción

El movimiento explica la navegación y nada más. 

- Navegación hacia dentro y hacia atrás: transición push (MOVE\_IN / MOVE\_OUT) de 0,3 s.
- Cambio de pestaña: instantáneo, sin transición.
- Cambios de estado de un componente (cantidad, chip, interruptor): Smart Animate de 0,15 s.
- Cambio de tema: fundido de 0,2 a 0,3 s.
- Scroll solo vertical; el menú web queda fijo.
- Con «Reducir movimiento» activado, todas las transiciones pasan a ser un fundido.

