import { api, type ApiHistorial, type ApiPrecio, type ApiProductoDetalle } from '@/api/cliente';
import { rag, type Equivalente } from '@/api/rag';
import { usePeticion } from '@/api/use-peticion';
import { fechaCorta } from '@/utils/meses';

export type ProductoApi = {
  producto: ApiProductoDetalle;
  historial: ApiHistorial;
  /** El mismo producto en cada otra cadena (vacío si la comparación falla). */
  otrasCadenas: Equivalente[];
};

/** Por debajo de esta confianza, el equivalente de `/equiv` no se enseña. */
const CONFIANZA_MINIMA = 0.5;

/**
 * Equivalentes en el resto de cadenas de la API: `/equiv` del asistente, una petición por cadena
 * y en paralelo. Una cadena que falle no impide las demás.
 */
async function equivalentes(producto: ApiProductoDetalle, signal: AbortSignal) {
  const cadenas = await api.cadenas(signal);
  const otras = cadenas.filter((c) => c.slug !== producto.chain.slug);
  const resultados = await Promise.allSettled(
    otras.map((c) => rag.equivalente(String(producto.id), c.slug, signal)),
  );
  return resultados.flatMap((r) =>
    r.status === 'fulfilled' && r.value && r.value.confianza >= CONFIANZA_MINIMA ? [r.value] : [],
  );
}

/**
 * Ficha, historial y comparación entre cadenas a la vez. La API aún no agrupa el mismo producto
 * entre cadenas: el asistente elige el equivalente en cada una. Si falla, la ficha sale igual.
 */
export function useProductoApi(id: string, { comparar = true, activa = true } = {}) {
  return usePeticion<ProductoApi>(
    async (signal) => {
      const [producto, historial] = await Promise.all([
        api.producto(id, signal),
        api.historial(id, signal),
      ]);
      const otrasCadenas = comparar ? await equivalentes(producto, signal).catch(() => []) : [];
      return { producto, historial, otrasCadenas };
    },
    [id, comparar],
    { activa },
  );
}

export type SerieGrafica = {
  valores: number[];
  eje: [string, string, string];
  maximo: { precio: number; mes: string };
  minimo: number;
  media: number;
  guias: number[];
};

/**
 * Historial de la API (del más antiguo al más reciente) → datos de GraficaPrecio. Usa el precio
 * del envase. `desde` (YYYY-MM-DD) recorta el periodo. Con menos de dos puntos no hay gráfica.
 */
export function serieDesdeHistorial(puntos: ApiPrecio[], desde?: string): SerieGrafica | null {
  const validos = puntos.filter(
    (p): p is ApiPrecio & { total: number } =>
      p.total != null && (!desde || p.observed_on >= desde),
  );
  if (validos.length < 2) return null;

  const valores = validos.map((p) => p.total);
  const iMax = valores.indexOf(Math.max(...valores));
  const max = valores[iMax];
  const min = Math.min(...valores);
  const mitad = validos[Math.floor((validos.length - 1) / 2)];
  // Guías en euros enteros por encima y por debajo de la línea.
  const guias = [...new Set([Math.ceil(max), Math.floor(min)])].filter((g) => g > 0);

  return {
    valores,
    eje: [
      fechaCorta(validos[0].observed_on, false),
      fechaCorta(mitad.observed_on, false),
      fechaCorta(validos[validos.length - 1].observed_on, false),
    ],
    maximo: { precio: max, mes: fechaCorta(validos[iMax].observed_on, false) },
    minimo: min,
    media: valores.reduce((a, b) => a + b, 0) / valores.length,
    guias: guias.length ? guias : [Math.round(max)],
  };
}

/** «53 % menos que en nov 2024» si hoy está por debajo del máximo del historial. */
export function tendenciaDesdeSerie(serie: SerieGrafica | null, actual: number) {
  if (!serie || actual >= serie.maximo.precio) return null;
  const porcentaje = Math.round((1 - actual / serie.maximo.precio) * 100);
  return porcentaje > 0 ? `${porcentaje} % menos que en ${serie.maximo.mes}` : null;
}
