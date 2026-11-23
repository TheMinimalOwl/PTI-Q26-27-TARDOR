import type { ApiLinea, ApiListaOptimizada, ApiProductoResumen } from '@/api/cliente';
import type { ProductoCatalogo } from '@/data/datos-ejemplo';
import { formatoPrecioUnidad } from '@/utils/formato';

/** «3,45 €/l» del último precio de un producto de la API. */
export const precioPorUnidad = (p: Pick<ApiProductoResumen, 'price' | 'unit'>) =>
  formatoPrecioUnidad(p.price?.unit_price, p.unit);

/**
 * Resumen de la API → fila de catálogo. Cada producto de la API es de una sola cadena (aún no
 * agrupa el mismo producto entre cadenas), por eso `cadenasCon` es 1. Sin precio no se muestra.
 */
export function aProductoCatalogo(p: ApiProductoResumen): ProductoCatalogo | null {
  if (p.price?.total == null) return null;
  return {
    id: String(p.id),
    nombre: p.name,
    formato: '',
    cadena: p.chain.slug,
    precio: p.price.total,
    precioUnidad: precioPorUnidad(p),
    cadenasCon: 1,
  };
}

/** La lista entera en una cadena. Las claves de `precios` y `productos` son ids de la lista. */
export type CestaCadena = {
  cadena: string;
  total: number;
  tiene: number;
  /** Ids de los productos de la lista que esta cadena no tiene. */
  falta: string[];
  /** Subtotal de cada producto de la lista en esta cadena (precio × unidades). */
  precios: Record<string, number>;
  /** Nombre del producto que se compraría, si es distinto del de la lista (modo API). */
  productos: Record<string, string>;
};

export type ResumenCesta = {
  productos: number;
  /** Cadenas con toda la lista, de la más barata a la más cara. */
  completas: (CestaCadena & { diferencia: number })[];
  /** Cadenas a las que les falta algo, con más productos primero. */
  incompletas: CestaCadena[];
  /** Cada producto donde sale más barato, agrupado por tienda. */
  repartida: { total: number; ahorro: number | null; tiendas: CestaCadena[] };
};

/** Ordena y calcula diferencias y ahorro a partir de las cestas por cadena y la repartida. */
export function resumir(
  cestas: CestaCadena[],
  tiendas: CestaCadena[],
  productos: number,
  ahorro?: number | null,
): ResumenCesta {
  const completas = cestas.filter((c) => c.falta.length === 0).sort((a, b) => a.total - b.total);
  const incompletas = cestas
    .filter((c) => c.falta.length > 0 && c.tiene > 0)
    .sort((a, b) => b.tiene - a.tiene || a.total - b.total);
  const mejor = completas[0]?.total;
  const total = tiendas.reduce((s, t) => s + t.total, 0);
  return {
    productos,
    completas: completas.map((c) => ({ ...c, diferencia: c.total - completas[0].total })),
    incompletas,
    repartida: {
      total,
      ahorro: ahorro !== undefined ? ahorro : mejor !== undefined ? mejor - total : null,
      tiendas,
    },
  };
}

/**
 * `/shopping-list/optimize` → ResumenCesta. `idPorConsulta` traduce cada `q` enviado al id del
 * producto de la lista.
 */
export function resumenDesdeOptimizada(
  r: ApiListaOptimizada,
  idPorConsulta: Record<string, string>,
  productos: number,
): ResumenCesta {
  const id = (q: string) => idPorConsulta[q] ?? q;
  const aCesta = (cadena: string, total: number, lineas: ApiLinea[], falta: string[]) => ({
    cadena,
    total,
    tiene: lineas.length,
    falta: falta.map(id),
    precios: Object.fromEntries(lineas.map((l) => [id(l.q), l.subtotal])),
    productos: Object.fromEntries(lineas.map((l) => [id(l.q), l.product.name])),
  });

  const cestas = r.baskets.map((b) => aCesta(b.chain.slug, b.total, b.lines, b.missing));
  const porCadena = new Map<string, ApiLinea[]>();
  for (const l of r.combined.lines) {
    const slug = l.product.chain.slug;
    porCadena.set(slug, [...(porCadena.get(slug) ?? []), l]);
  }
  const tiendas = [...porCadena].map(([cadena, lineas]) =>
    aCesta(
      cadena,
      lineas.reduce((s, l) => s + l.subtotal, 0),
      lineas,
      [],
    ),
  );
  return resumir(cestas, tiendas, productos, r.savings);
}
