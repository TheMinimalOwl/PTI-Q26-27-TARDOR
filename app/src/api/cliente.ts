/**
 * Cliente de la API de catálogo (pti-repo: rama `api`, con la lista optimizada y la búsqueda
 * semántica integradas en `develop`; contrato en api/docs/CONTRATO.md y api/openapi.json).
 */
import { consulta, pedirJson } from '@/api/http';

/** Para probar con la API en local: EXPO_PUBLIC_API_URL=http://<ip-del-pc>:8000 */
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'https://api.superahorro.app').replace(
  /\/$/,
  '',
);

// Tipos del contrato (api/app/schemas.py)

export type ApiCadena = { slug: string; name: string };

export type ApiPrecio = {
  observed_on: string;
  store: string;
  total: number | null;
  unit_price: number | null;
  unit_src: string;
};

export type ApiProductoResumen = {
  id: number;
  name: string;
  chain: ApiCadena;
  category: string;
  unit: string | null;
  url: string;
  price: ApiPrecio | null;
};

export type ApiProductoDetalle = ApiProductoResumen & {
  source_id: string;
  size: string;
  size_format: string;
  updated_at: string;
};

export type ApiPaginaBusqueda = {
  query: string;
  /** Unidad que va primero en `items`: los precios unitarios solo se comparan dentro de ella. */
  unit: string | null;
  total: number;
  limit: number;
  offset: number;
  items: ApiProductoResumen[];
};

export type ApiResultadoSemantico = { items: (ApiProductoResumen & { similarity: number })[] };

export type ApiHistorial = { product_id: number; unit: string | null; points: ApiPrecio[] };

export type ApiArticuloLista = { q: string; quantity?: number; amount?: number; unit?: string };

export type ApiLinea = {
  q: string;
  amount: number | null;
  packs: number;
  product: ApiProductoResumen;
  subtotal: number;
};

export type ApiCesta = { total: number; found: number; missing: string[]; lines: ApiLinea[] };

export type ApiListaOptimizada = {
  best_chain: string | null;
  best_total: number | null;
  combined_total: number;
  /** null si la combinada y la mejor cadena no son comparables (faltan artículos distintos). */
  savings: number | null;
  combined: ApiCesta;
  /** Primero las que tienen más artículos y, entre ellas, la más barata. */
  baskets: (ApiCesta & { chain: ApiCadena })[];
};

const pedir = <T>(ruta: string, signal?: AbortSignal, cuerpo?: unknown) =>
  pedirJson<T>(`${API_URL}${ruta}`, { signal, cuerpo });

export const api = {
  cadenas: (signal?: AbortSignal) => pedir<ApiCadena[]>('/chains', signal),
  buscar: (q: string, signal?: AbortSignal, limit = 50) =>
    pedir<ApiPaginaBusqueda>(`/products/search${consulta({ q, limit })}`, signal),
  /** Productos parecidos aunque no compartan palabras (embeddings de la IA). */
  buscarParecidos: (q: string, signal?: AbortSignal, top_k = 10) =>
    pedir<ApiResultadoSemantico>(`/products/semantic-search${consulta({ q, top_k })}`, signal),
  producto: (id: string, signal?: AbortSignal) =>
    pedir<ApiProductoDetalle>(`/products/${encodeURIComponent(id)}`, signal),
  historial: (id: string, signal?: AbortSignal) =>
    pedir<ApiHistorial>(`/products/${encodeURIComponent(id)}/prices`, signal),
  optimizarLista: (items: ApiArticuloLista[], signal?: AbortSignal) =>
    pedir<ApiListaOptimizada>('/shopping-list/optimize', signal, { items }),
};

/** Los ids de la API son números; los de los datos de prueba, palabras («aceite»). */
export const esIdApi = (id: string) => /^\d+$/.test(id);
