import { resumenDesdeOptimizada, resumir, type CestaCadena, type ResumenCesta } from '@/api/adaptadores';
import { api, type ApiArticuloLista } from '@/api/cliente';
import { usePeticion, type EstadoPeticion } from '@/api/use-peticion';
import { Cadenas } from '@/constants/theme';
import { preciosPorCadena, tiendas, type ProductoLista } from '@/data/datos-ejemplo';
import { cantidadDe, consultaDe, useLista } from '@/data/estado-lista';
import { useModoApi } from '@/data/fuente-datos';
import { esCadenaConocida, formatoPrecio, nombreCadena, plural } from '@/utils/formato';

/** Comparación de la lista con los precios de prueba (tabla de W4). */
export function resumenDePrueba(lista: ProductoLista[]): ResumenCesta {
  const cestas: CestaCadena[] = Cadenas.map(({ id: cadena }) => {
    const precios: Record<string, number> = {};
    const falta: string[] = [];
    for (const p of lista) {
      const precio = preciosPorCadena[p.id]?.[cadena];
      if (precio === undefined) falta.push(p.id);
      else precios[p.id] = precio * p.cantidad;
    }
    const total = Object.values(precios).reduce((s, v) => s + v, 0);
    return { cadena, total, tiene: lista.length - falta.length, falta, precios, productos: {} };
  });

  // Repartida: cada producto en la cadena donde es más barato, agrupado por tienda en el orden fijo.
  const mejorDe = (id: string) =>
    cestas
      .filter((c) => c.precios[id] !== undefined)
      .reduce<CestaCadena | null>((m, c) => (!m || c.precios[id] < m.precios[id] ? c : m), null);
  const tiendas = new Map<string, CestaCadena>();
  for (const p of lista) {
    const mejor = mejorDe(p.id);
    if (!mejor) continue;
    const t = tiendas.get(mejor.cadena) ?? {
      cadena: mejor.cadena,
      total: 0,
      tiene: 0,
      falta: [],
      precios: {},
      productos: {},
    };
    t.precios[p.id] = mejor.precios[p.id];
    t.total += mejor.precios[p.id];
    t.tiene += 1;
    tiendas.set(mejor.cadena, t);
  }
  const ordenadas = Cadenas.flatMap((c) => tiendas.get(c.id) ?? []);
  return resumir(cestas, ordenadas, lista.length);
}

/**
 * Cuánto cuesta la lista en cada cadena y repartida. Con la API, `/shopping-list/optimize` con
 * una consulta por producto (ver consultaDe); con datos de prueba, la tabla de W4.
 */
export function useCesta(): EstadoPeticion<ResumenCesta> & { lista: ProductoLista[] } {
  const lista = useLista();
  const modoApi = useModoApi();

  // Con el formato se pide la cantidad (`amount`): todas las cadenas se comparan por los mismos
  // litros o kilos y no entran productos de otra unidad. Dos productos con la misma consulta y
  // unidad se piden juntos sumando cantidades.
  const articulos = new Map<string, ApiArticuloLista & { id: string }>();
  for (const p of lista) {
    const q = consultaDe(p.nombre) || p.nombre.toLowerCase();
    const medida = cantidadDe(p.formato);
    const previo = articulos.get(q);
    articulos.set(
      q,
      medida
        ? { q, id: previo?.id ?? p.id, unit: medida.unidad, amount: (previo?.amount ?? 0) + medida.cantidad * p.cantidad }
        : { q, id: previo?.id ?? p.id, quantity: (previo?.quantity ?? 0) + p.cantidad },
    );
  }
  const items = [...articulos.values()];

  const peticion = usePeticion(
    async (signal) => {
      const r = await api.optimizarLista(
        items.map(({ id: _id, ...articulo }) => articulo),
        signal,
      );
      return resumenDesdeOptimizada(
        r,
        Object.fromEntries(items.map((i) => [i.q, i.id])),
        items.length,
      );
    },
    [items],
    { activa: modoApi && items.length > 0 },
  );

  if (!modoApi || items.length === 0) {
    return { estado: 'ok', datos: resumenDePrueba(lista), reintentar: () => {}, lista };
  }
  return { ...peticion, lista };
}

/** «a 650 m» hasta la tienda de ejemplo de la cadena, si la hay. */
export const distanciaA = (cadena: string) =>
  esCadenaConocida(cadena) ? tiendas[cadena].distancia : undefined;

/** «falta 1», «faltan 3». */
export const textoFalta = (n: number) => (n === 1 ? 'falta 1' : `faltan ${n}`);

/** «Repartida en 4 tiendas: 18,90 €, 0,48 € menos que en Bonarea». */
export function textoRepartida({ repartida, completas }: ResumenCesta) {
  const base = `Repartida en ${plural(repartida.tiendas.length, 'tienda')}: ${formatoPrecio(repartida.total)}`;
  const mejor = completas[0];
  return repartida.ahorro && repartida.ahorro > 0 && mejor
    ? `${base}, ${formatoPrecio(repartida.ahorro)} menos que en ${nombreCadena(mejor.cadena)}`
    : base;
}
