import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';

/** Colores del modo actual (claro u oscuro). */
export function useTheme() {
  return Colors[useColorScheme()];
}
