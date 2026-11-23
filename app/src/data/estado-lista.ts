import { crearAlmacen } from '@/data/almacen';
import { listaSemana, type ProductoLista } from '@/data/datos-ejemplo';

/** La lista de la compra: la usan Lista, Inicio, Comparar, Ruta y el menú de la web. */
const lista = crearAlmacen<ProductoLista[]>(listaSemana, 'sa.lista');

export const useLista = lista.use;

const PALABRAS_VACIAS = new Set(['de', 'del', 'la', 'el', 'los', 'las', 'con', 'sin', 'y', 'en', 'al']);

/**
 * Qué se pide a `/shopping-list/optimize` por cada producto: las dos primeras palabras con
 * sentido del nombre («Leche semidesnatada Pascual 6 × 1 l» → «leche semidesnatada»). Así cada
 * cadena compara su versión más barata del mismo producto y no solo la marca exacta.
 */
export function consultaDe(nombre: string) {
  return nombre
    .toLowerCase()
    .split(/[\s,]+/)
    .filter((p) => /^\p{L}{2,}$/u.test(p) && !PALABRAS_VACIAS.has(p))
    .slice(0, 2)
    .join(' ');
}

/** Gramos, mililitros… → la unidad de la API (kg, l, ud) y su factor. */
const UNIDADES: Record<string, { unidad: string; factor: number }> = {
  kg: { unidad: 'kg', factor: 1 },
  g: { unidad: 'kg', factor: 0.001 },
  l: { unidad: 'l', factor: 1 },
  cl: { unidad: 'l', factor: 0.01 },
  ml: { unidad: 'l', factor: 0.001 },
  u: { unidad: 'ud', factor: 1 },
  ud: { unidad: 'ud', factor: 1 },
  uds: { unidad: 'ud', factor: 1 },
  dz: { unidad: 'ud', factor: 12 },
};

/**
 * «1 l», «6 × 1 l», «500 g», «0.75 L», «12 u» → { cantidad: 6, unidad: 'l' }. La lista optimizada
 * compara así todas las cadenas por la misma cantidad (`amount`). null si no se entiende.
 */
export function cantidadDe(formato: string) {
  const m = /^(?:(\d+)\s*[×x]\s*)?(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)$/.exec(formato.trim());
  const unidad = m && UNIDADES[m[3].toLowerCase()];
  if (!m || !unidad) return null;
  const cantidad = Number(m[1] ?? 1) * Number(m[2].replace(',', '.')) * unidad.factor;
  return cantidad > 0 ? { cantidad: Math.round(cantidad * 1000) / 1000, unidad: unidad.unidad } : null;
}

export function anadirALista(producto: Omit<ProductoLista, 'cantidad'>) {
  lista.set((actual) =>
    actual.some((p) => p.id === producto.id)
      ? actual.map((p) => (p.id === producto.id ? { ...p, cantidad: p.cantidad + 1 } : p))
      : [...actual, { ...producto, cantidad: 1 }],
  );
}

/** Con cantidad 0 o menos el producto sale de la lista. */
export function cambiarCantidad(id: string, cantidad: number) {
  lista.set((actual) =>
    cantidad <= 0
      ? actual.filter((p) => p.id !== id)
      : actual.map((p) => (p.id === id ? { ...p, cantidad } : p)),
  );
}

export const estaEnLista = (productos: ProductoLista[], id: string) =>
  productos.some((p) => p.id === id);
