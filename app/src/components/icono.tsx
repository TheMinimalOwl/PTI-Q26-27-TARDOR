import { SymbolView } from 'expo-symbols';

import { useTheme } from '@/hooks/use-theme';
import type { ThemeColor } from '@/constants/theme';

const simbolos = {
  campana: { ios: 'bell', android: 'notifications', web: 'notifications' },
  buscar: { ios: 'magnifyingglass', android: 'search', web: 'search' },
  codigo: { ios: 'barcode.viewfinder', android: 'barcode_scanner', web: 'barcode_scanner' },
  preguntar: { ios: 'bubble.left', android: 'chat_bubble', web: 'chat_bubble' },
  siguiente: { ios: 'chevron.right', android: 'chevron_right', web: 'chevron_right' },
  compartir: { ios: 'square.and.arrow.up', android: 'ios_share', web: 'ios_share' },
  papelera: { ios: 'trash', android: 'delete', web: 'delete' },
  mas: { ios: 'plus', android: 'add', web: 'add' },
  menos: { ios: 'minus', android: 'remove', web: 'remove' },
  cerrar: { ios: 'xmark', android: 'close', web: 'close' },
  ojo: { ios: 'eye', android: 'visibility', web: 'visibility' },
  ojoTachado: { ios: 'eye.slash', android: 'visibility_off', web: 'visibility_off' },
  filtros: { ios: 'slider.horizontal.3', android: 'tune', web: 'tune' },
  desplegar: { ios: 'chevron.down', android: 'expand_more', web: 'expand_more' },
  hecho: { ios: 'checkmark', android: 'check', web: 'check' },
  bajada: { ios: 'chart.line.downtrend.xyaxis', android: 'trending_down', web: 'trending_down' },
  alerta: { ios: 'exclamationmark.circle', android: 'error', web: 'error' },
  micro: { ios: 'mic', android: 'mic', web: 'mic' },
  enviar: { ios: 'arrow.up', android: 'arrow_upward', web: 'arrow_upward' },
  sinConexion: { ios: 'wifi.slash', android: 'wifi_off', web: 'wifi_off' },
  atras: { ios: 'chevron.left', android: 'arrow_back', web: 'arrow_back' },
  zona: { ios: 'scope', android: 'my_location', web: 'my_location' },
  tiendas: { ios: 'mappin.and.ellipse', android: 'location_on', web: 'location_on' },
  luna: { ios: 'moon', android: 'dark_mode', web: 'dark_mode' },
  candado: { ios: 'lock', android: 'lock', web: 'lock' },
  salir: { ios: 'rectangle.portrait.and.arrow.right', android: 'logout', web: 'logout' },
  info: { ios: 'info.circle', android: 'info', web: 'info' },
  reloj: { ios: 'clock', android: 'schedule', web: 'schedule' },
  nube: { ios: 'icloud', android: 'cloud', web: 'cloud' },
  cuenta: { ios: 'person', android: 'person', web: 'person' },
  sol: { ios: 'sun.max', android: 'light_mode', web: 'light_mode' },
  lista: { ios: 'checklist', android: 'checklist', web: 'checklist' },
  menu: { ios: 'line.3.horizontal', android: 'menu', web: 'menu' },
} as const;

export type NombreIcono = keyof typeof simbolos;

type Props = { nombre: NombreIcono; size?: number; themeColor?: ThemeColor };

export function Icono({ nombre, size = 24, themeColor = 'text' }: Props) {
  const theme = useTheme();
  return <SymbolView name={simbolos[nombre]} size={size} tintColor={theme[themeColor]} />;
}
