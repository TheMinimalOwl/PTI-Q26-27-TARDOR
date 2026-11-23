import { Appearance, Platform } from 'react-native';

import { crearAlmacen } from '@/data/almacen';
import { apariencia } from '@/data/datos-ejemplo';

export type Tema = (typeof apariencia.opciones)[number]['valor'];

const tema = crearAlmacen<Tema>(apariencia.inicial, 'sa.tema');

export const useTema = tema.use;

/**
 * Cambia el modo de toda la app. useColorScheme() lee este valor, así que vale en todas las
 * plataformas; en el móvil además se avisa al sistema para que los controles nativos (Switch,
 * mapa, teclado) cambien. react-native-web no tiene Appearance.setColorScheme.
 */
export function setTema(nuevo: Tema) {
  tema.set(nuevo);
  if (Platform.OS !== 'web') Appearance.setColorScheme(nuevo === 'auto' ? 'unspecified' : nuevo);
}
