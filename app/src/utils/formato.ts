import { Cadenas, type CadenaId } from '@/constants/theme';

/** 3,97 -> «3,97 €». Sin Intl: Hermes en Android no siempre trae es-ES. */
export function formatoPrecio(valor: number): string {
  return `${valor.toFixed(2).replace('.', ',')} €`;
}

/** «3,45 €/l»; vacío si falta el precio o la unidad. */
export function formatoPrecioUnidad(valor: number | null | undefined, unidad: string | null) {
  return valor != null && unidad ? `${formatoPrecio(valor)}/${unidad}` : '';
}

/** Nombre visible de una cadena. Una cadena que la app aún no conoce sale con su slug en mayúscula. */
export function nombreCadena(id: string) {
  return Cadenas.find((c) => c.id === id)?.nombre ?? id.charAt(0).toUpperCase() + id.slice(1);
}

export const esCadenaConocida = (id: string): id is CadenaId => Cadenas.some((c) => c.id === id);

export const totalCadenas = Cadenas.length;

/** ['a', 'b', 'c'] -> «a, b y c». */
export function enumerar(textos: string[]) {
  return textos.length > 1
    ? `${textos.slice(0, -1).join(', ')} y ${textos[textos.length - 1]}`
    : (textos[0] ?? '');
}

/** «1 producto», «3 productos». */
export const plural = (n: number, singular: string, varios = `${singular}s`) =>
  `${n} ${n === 1 ? singular : varios}`;
