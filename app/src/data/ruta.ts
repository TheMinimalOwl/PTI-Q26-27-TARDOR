import type { ResumenCesta } from '@/api/adaptadores';
import { tiendas, type Coordenadas, type ProductoLista } from '@/data/datos-ejemplo';
import { consultaDe } from '@/data/estado-lista';
import { enumerar, esCadenaConocida } from '@/utils/formato';

export type Parada = {
  cadena: string;
  direccion: string;
  /** «leche», «pollo y huevos». */
  productos: string;
  total: number;
  unidades: number;
  /** null: cadena sin tienda conocida (no sale en el mapa). */
  coordenadas: Coordenadas | null;
};

/**
 * Paradas de la compra repartida, ordenadas de norte a sur (un recorrido sencillo sin cálculo
 * de rutas). Las tiendas son las de ejemplo de Gràcia: la API aún no expone tiendas.
 */
export function paradasDe(resumen: ResumenCesta, lista: ProductoLista[]): Parada[] {
  const nombre = (id: string) => {
    const p = lista.find((x) => x.id === id);
    return p ? consultaDe(p.nombre).split(' ')[0] || p.nombre : id;
  };
  return resumen.repartida.tiendas
    .map((t) => {
      const tienda = esCadenaConocida(t.cadena) ? tiendas[t.cadena] : null;
      const ids = Object.keys(t.precios);
      return {
        cadena: t.cadena,
        direccion: tienda?.direccion ?? 'Tienda sin ubicar',
        productos: enumerar(ids.map(nombre)),
        total: t.total,
        unidades: ids.reduce((s, id) => s + (lista.find((p) => p.id === id)?.cantidad ?? 1), 0),
        coordenadas: tienda?.coordenadas ?? null,
      };
    })
    .sort((a, b) => (b.coordenadas?.latitude ?? -90) - (a.coordenadas?.latitude ?? -90));
}
