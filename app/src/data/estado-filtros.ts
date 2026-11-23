import type { CadenaId } from '@/constants/theme';
import { crearAlmacen } from '@/data/almacen';
import { filtros } from '@/data/datos-ejemplo';

/** Filtros de búsqueda compartidos entre Buscar, la hoja de filtros y la columna de la web. */
export type EstadoFiltros = { orden: string; cadenas: CadenaId[] };

export const filtrosIniciales: EstadoFiltros = {
  orden: filtros.ordenInicial,
  cadenas: filtros.cadenasIniciales,
};

const estado = crearAlmacen<EstadoFiltros>(filtrosIniciales);

export const setFiltros = estado.set;
export const useFiltros = estado.use;
export const filtrosVacios: EstadoFiltros = { orden: filtros.ordenInicial, cadenas: [] };
