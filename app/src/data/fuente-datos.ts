import { crearAlmacen } from '@/data/almacen';

/** De dónde salen los datos: las APIs (catálogo y asistente) o los datos de prueba de `datos-ejemplo.ts`. */
export type FuenteDatos = 'api' | 'prueba';

const fuente = crearAlmacen<FuenteDatos>('api', 'sa.fuente');

export const setFuenteDatos = fuente.set;
export const useFuenteDatos = fuente.use;
export const useModoApi = () => fuente.use() === 'api';
