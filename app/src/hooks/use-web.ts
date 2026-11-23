import { Platform, useWindowDimensions } from 'react-native';

import { Web } from '@/constants/theme';
import { useHidratado } from '@/hooks/use-hidratado';

/**
 * Web ancha (03 · Web, 1440): tablas y columnas. La web estrecha (390) usa las pantallas del
 * móvil. El servidor no sabe el ancho: hasta hidratar se pinta la versión estrecha.
 */
export function useEscritorio() {
  const { width } = useWindowDimensions();
  const hidratado = useHidratado();
  return Platform.OS === 'web' && hidratado && width >= Web.anchoEscritorio;
}

/** Alto del menú superior de la web, que va encima del contenido; 0 en el móvil. */
export function useAltoMenuWeb() {
  const escritorio = useEscritorio();
  if (Platform.OS !== 'web') return 0;
  return escritorio ? Web.altoMenu : Web.altoMenuEstrecho;
}
