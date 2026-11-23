import { precioPorUnidad } from '@/api/adaptadores';
import { esIdApi, type ApiPrecio } from '@/api/cliente';
import { serieDesdeHistorial, tendenciaDesdeSerie, useProductoApi, type ProductoApi } from '@/api/producto';
import type { EstadoPeticion } from '@/api/use-peticion';
import { Cadenas } from '@/constants/theme';
import { detallesProducto, type DetalleProducto, type ProductoLista } from '@/data/datos-ejemplo';
import { useModoApi } from '@/data/fuente-datos';
import { formatoPrecio, formatoPrecioUnidad, nombreCadena, totalCadenas } from '@/utils/formato';
import { fechaCorta } from '@/utils/meses';

/** Precio en una cadena para la tabla «Precio por cadena». */
export type FilaFicha = {
  cadena: string;
  precio?: number;
  precioUnidad?: string;
  oferta?: string;
  /** Tienda más cercana (prueba) o producto que se compraría en esa cadena (API). */
  detalle?: string;
  /** Id de la API del producto de esa cadena, para abrir su ficha. */
  idProducto?: string;
};

export type FichaProducto = {
  id: string;
  nombre: string;
  nombreCompleto: string;
  /** Marca y formato (prueba) o categoría (API). */
  detalle: string;
  formato: string;
  categoria?: string;
  mejor: { cadena: string; precio: number } | null;
  tendencia: string | null;
  /** Una fila por cadena: primero las 5 en su orden fijo y después las que la app no conoce. */
  filas: FilaFicha[];
  /** Título de la columna `detalle` en la tabla web. */
  columnaDetalle: string;
  /** Nota bajo la tabla (p. ej. si la comparación entre cadenas no está). */
  nota?: string;
  /** Historial de precios, del más antiguo al más reciente. */
  puntos: ApiPrecio[];
  subtituloEvolucion: string;
  avisoBajoDe?: number;
  /** Lo que se guarda en la lista al pulsar «Añadir a la lista». */
  paraLista: Omit<ProductoLista, 'cantidad'>;
  compartir: string;
};

const ordenFijo = (cadena: string) => {
  const i = Cadenas.findIndex((c) => c.id === cadena);
  return i === -1 ? Cadenas.length : i;
};

function fichaDePrueba(p: DetalleProducto): FichaProducto {
  const { mensual, primerMes } = p.evolucion;
  // La serie mensual de Figma pasada a fechas, como el historial de la API.
  const puntos: ApiPrecio[] = mensual.map((total, i) => {
    const mes = primerMes.mes + i;
    const fecha = `${primerMes.anio + Math.floor(mes / 12)}-${String((mes % 12) + 1).padStart(2, '0')}-01`;
    return { observed_on: fecha, store: '', total, unit_price: null, unit_src: '-' };
  });
  return {
    id: p.id,
    nombre: p.nombre,
    nombreCompleto: p.nombreCompleto,
    detalle: p.marcaFormato,
    formato: p.formato,
    categoria: 'Aceites',
    mejor: p.mejor,
    tendencia: p.tendencia,
    filas: Cadenas.map((c) => {
      const fila = p.precios.find((f) => f.cadena === c.id);
      return {
        cadena: c.id,
        precio: fila?.precio,
        precioUnidad: fila?.precioUnidad,
        oferta: fila?.oferta,
        detalle: fila?.tienda,
      };
    }),
    columnaDetalle: 'Tienda más cercana',
    puntos,
    subtituloEvolucion: `Precio más barato entre las ${totalCadenas} cadenas, cada mes`,
    avisoBajoDe: p.evolucion.avisoBajoDe,
    paraLista: {
      id: p.id,
      nombre: p.nombreCompleto,
      formato: p.formato,
      precio: p.mejor.precio,
      cadena: p.mejor.cadena,
    },
    compartir: `${p.nombre}: ${formatoPrecio(p.mejor.precio)} en ${nombreCadena(p.mejor.cadena)}`,
  };
}

function fichaDeApi({ producto, historial, otrasCadenas }: ProductoApi): FichaProducto {
  const total = producto.price?.total ?? null;
  const propia: FilaFicha & { valorUnidad?: number } = {
    cadena: producto.chain.slug,
    precio: total ?? undefined,
    precioUnidad: precioPorUnidad(producto) || undefined,
    valorUnidad: producto.price?.unit_price ?? undefined,
    detalle: producto.price ? `Precio del ${fechaCorta(producto.price.observed_on)}` : undefined,
  };
  // De las otras cadenas, el equivalente que elige el asistente (`/equiv`).
  const otras = otrasCadenas
    .filter((e) => e.cadena !== producto.chain.slug && e.precio !== null)
    .map((e) => ({
      cadena: e.cadena,
      precio: e.precio ?? undefined,
      precioUnidad: formatoPrecioUnidad(e.precioUnidad, e.unidad) || undefined,
      valorUnidad: e.unidad === producto.unit ? (e.precioUnidad ?? undefined) : undefined,
      detalle: e.nombre,
      idProducto: e.id,
    }));
  const filas = [propia, ...otras].sort((a, b) => ordenFijo(a.cadena) - ordenFijo(b.cadena));
  // «Más barato» compara el precio de una unidad (todas son de la misma unidad).
  const mejor = [propia, ...otras]
    .filter((f) => f.precio !== undefined)
    .reduce<(typeof otras)[number] | typeof propia | null>(
      (m, f) => (!m || (f.valorUnidad ?? Infinity) < (m.valorUnidad ?? Infinity) ? f : m),
      null,
    );
  const serie = serieDesdeHistorial(historial.points);
  const formato = [producto.size, producto.size_format].filter(Boolean).join(' ').trim();

  return {
    id: String(producto.id),
    nombre: producto.name,
    nombreCompleto: producto.name,
    detalle: producto.category,
    formato,
    categoria: producto.category || undefined,
    mejor: mejor?.precio !== undefined ? { cadena: mejor.cadena, precio: mejor.precio } : null,
    // El historial es el de este producto: solo vale si el más barato es él mismo.
    tendencia:
      total != null && mejor === propia ? tendenciaDesdeSerie(serie, total) : null,
    filas: filas.map(({ valorUnidad: _v, ...f }) => f),
    columnaDetalle: 'Producto',
    nota:
      otras.length === 0
        ? 'Aún no comparamos este producto en las otras cadenas.'
        : 'En las otras cadenas, el producto equivalente que elige el asistente.',
    puntos: historial.points,
    subtituloEvolucion: `Precio en ${producto.chain.name}`,
    paraLista: {
      id: String(producto.id),
      nombre: producto.name,
      formato,
      precio: total ?? 0,
      cadena: producto.chain.slug,
    },
    compartir:
      total != null
        ? `${producto.name}: ${formatoPrecio(total)} en ${producto.chain.name}`
        : producto.name,
  };
}

/**
 * Ficha de producto (C1/W3) y su historial (C2). Con la fuente «API», los ids numéricos (los de
 * Buscar) se piden a la API; el resto son de los datos de prueba. `datos` es null si el producto
 * de prueba no existe.
 */
export function useFicha(
  id: string,
  { comparar = true } = {},
): EstadoPeticion<FichaProducto | null> {
  const desdeApi = useModoApi() && esIdApi(id);
  const peticion = useProductoApi(id, { comparar, activa: desdeApi });
  if (!desdeApi) {
    const prueba = detallesProducto[id];
    return {
      estado: 'ok',
      datos: prueba ? fichaDePrueba(prueba) : null,
      reintentar: peticion.reintentar,
    };
  }
  return peticion.estado === 'ok' ? { ...peticion, datos: fichaDeApi(peticion.datos) } : peticion;
}

/** Ids de las cadenas de la ficha, en orden de precio (la tabla de W3 va de más barato a más caro). */
export const filasPorPrecio = (filas: FilaFicha[]) =>
  [...filas].sort(
    (a, b) =>
      (a.precio ?? Infinity) - (b.precio ?? Infinity) || ordenFijo(a.cadena) - ordenFijo(b.cadena),
  );
