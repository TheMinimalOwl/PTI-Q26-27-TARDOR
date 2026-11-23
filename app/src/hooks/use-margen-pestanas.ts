import { Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BottomTabInset } from '@/constants/theme';

/**
 * Espacio que ocupa la barra de pestañas sobre el contenido. En iOS la barra nativa flota encima;
 * en Android las pestañas nativas ya colocan la pantalla por encima de la barra, así que es 0.
 */
export function useMargenPestanas() {
  const insets = useSafeAreaInsets();
  return Platform.OS === 'ios' ? BottomTabInset + insets.bottom : 0;
}
