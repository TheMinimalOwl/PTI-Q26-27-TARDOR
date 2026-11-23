import { useColorScheme as useEsquemaSistema } from 'react-native';

import { useTema } from '@/data/estado-apariencia';
import { useHidratado } from '@/hooks/use-hidratado';

/**
 * Modo claro u oscuro efectivo: el elegido en Apariencia o, en «Automática», el del sistema.
 * En la web el HTML del servidor sale en claro; hasta hidratar se mantiene claro.
 */
export function useColorScheme(): 'light' | 'dark' {
  const tema = useTema();
  const sistema = useEsquemaSistema();
  if (!useHidratado()) return 'light';
  if (tema !== 'auto') return tema;
  return sistema === 'dark' ? 'dark' : 'light';
}
