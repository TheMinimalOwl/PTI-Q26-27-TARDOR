import { aProductoCatalogo } from '@/api/adaptadores';
import { api, type ApiProductoResumen } from '@/api/cliente';
import { usePeticion, type EstadoPeticion } from '@/api/use-peticion';
import { busqueda, detallesProducto, filtros, type ProductoCatalogo } from '@/data/datos-ejemplo';
import { useFiltros } from '@/data/estado-filtros';
import { useModoApi } from '@/data/fuente-datos';
import { esCadenaConocida, plural } from '@/utils/formato';

export const MINIMO_LETRAS = 2;
/** Espera tras la última tecla antes de preguntar a la API. */
const ESPERA_API_MS = 350;
/** En modo prueba se simula la consulta para ver el estado de carga (B5). */
const ESPERA_PRUEBA_MS = 600;

export type ResultadoBusqueda = {
  productos: ProductoCatalogo[];
  /** Productos que encontró la fuente antes de aplicar filtros (la API pagina de 50 en 50). */
  total: number;
  /** Sin coincidencias por nombre: son productos parecidos de la búsqueda semántica. */
  parecidos: boolean;
};

const normalizar = (texto: string) =>
  texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');

const esperar = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolver) => {
    const t = setTimeout(resolver, ms);
    signal.addEventListener('abort', () => clearTimeout(t));
  });

const aCatalogo = (items: ApiProductoResumen[]) =>
  items.map(aProductoCatalogo).filter((p) => p !== null);

/** `/products/search`; si no hay nada, `/products/semantic-search` (embeddings de la IA). */
async function buscarEnApi(q: string, signal: AbortSignal): Promise<ResultadoBusqueda> {
  const pagina = await api.buscar(q, signal);
  if (pagina.items.length > 0) {
    return { productos: aCatalogo(pagina.items), total: pagina.total, parecidos: false };
  }
  const parecidos = await api.buscarParecidos(q, signal).catch(() => ({ items: [] }));
  return { productos: aCatalogo(parecidos.items), total: parecidos.items.length, parecidos: true };
}

/** Coinciden todas las palabras escritas, sin tildes ni mayúsculas. */
async function buscarEnPrueba(q: string, signal: AbortSignal): Promise<ResultadoBusqueda> {
  await esperar(ESPERA_PRUEBA_MS, signal);
  const palabras = normalizar(q).split(/\s+/).filter(Boolean);
  const productos = busqueda.resultados.filter((p) =>
    palabras.every((w) => normalizar(p.nombre).includes(w)),
  );
  return { productos, total: productos.length, parecidos: false };
}

/** «3,97 €/l» → 3.97 para ordenar los datos de prueba. */
const valorUnidad = (p: ProductoCatalogo) =>
  Number(p.precioUnidad.split(' ')[0]?.replace(',', '.')) || Infinity;

function ordenar(productos: ProductoCatalogo[], orden: string, modoApi: boolean) {
  const [porUnidad, porPrecio, porBajada] = filtros.ordenes;
  const copia = [...productos];
  // La API ya ordena por precio unitario, primero la unidad más frecuente (€/l y €/kg no se comparan).
  if (orden === porUnidad && !modoApi) copia.sort((a, b) => valorUnidad(a) - valorUnidad(b));
  if (orden === porPrecio) copia.sort((a, b) => a.precio - b.precio);
  if (orden === porBajada) copia.sort((a, b) => (b.bajada ?? 0) - (a.bajada ?? 0));
  return copia;
}

/**
 * Búsqueda de B2/W2 con los filtros de B3 aplicados. Las cadenas que la app aún no conoce no se
 * pueden filtrar: se muestran siempre.
 */
export function useBusqueda(consulta: string): EstadoPeticion<ResultadoBusqueda> {
  const modoApi = useModoApi();
  const { orden, cadenas } = useFiltros();
  const q = consulta.trim();

  const peticion = usePeticion(
    (signal) => (modoApi ? buscarEnApi(q, signal) : buscarEnPrueba(q, signal)),
    [q, modoApi],
    { activa: q.length >= MINIMO_LETRAS, espera: modoApi ? ESPERA_API_MS : 0 },
  );
  if (peticion.estado !== 'ok') return peticion;

  const visibles = peticion.datos.productos.filter(
    (p) => !esCadenaConocida(p.cadena) || cadenas.includes(p.cadena),
  );
  return {
    ...peticion,
    datos: { ...peticion.datos, productos: ordenar(visibles, orden, modoApi) },
  };
}

/** Precio en cada cadena que se conoce de un resultado (la tabla de W2 tiene una columna por cadena). */
export function preciosPorCadenaDe(p: ProductoCatalogo): Record<string, number> {
  const detalle = detallesProducto[p.id];
  if (!detalle) return { [p.cadena]: p.precio };
  return Object.fromEntries(
    detalle.precios.flatMap((f) => (f.precio === undefined ? [] : [[f.cadena, f.precio]])),
  );
}

/** «23 productos», «50 de 120 productos» o «Sin coincidencias exactas: 8 productos parecidos». */
export function textoRecuento(visibles: number, total: number, parecidos: boolean) {
  if (parecidos) {
    return `Sin coincidencias exactas: ${plural(visibles, 'producto parecido', 'productos parecidos')}`;
  }
  return total > visibles ? `${visibles} de ${plural(total, 'producto')}` : plural(visibles, 'producto');
}
