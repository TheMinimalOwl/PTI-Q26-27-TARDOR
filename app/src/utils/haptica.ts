import * as Haptics from 'expo-haptics';
import { Platform, Vibration } from 'react-native';

let ultimaPulsacion = 0;
/** Un cambio de pantalla justo tras pulsar un botón ya tiene su toque; no se repite. */
const MARGEN_MS = 400;

/**
 * Algunas versiones de Expo Go en Android no traen el módulo nativo de expo-haptics y la
 * llamada falla. Entonces se usa una vibración muy corta del sistema; nunca rompe la app.
 */
function vibrar(intento: () => Promise<void>, milisegundos: number) {
  if (Platform.OS === 'web') return;
  try {
    intento().catch(() => Platform.OS === 'android' && Vibration.vibrate(milisegundos));
  } catch {
    if (Platform.OS === 'android') Vibration.vibrate(milisegundos);
  }
}

/** Toque corto al pulsar un control. */
export function hapticaPulsar() {
  ultimaPulsacion = Date.now();
  vibrar(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light), 12);
}

/** Toque de selección al cambiar de pantalla o pestaña (también con el gesto de atrás). */
export function hapticaCambio() {
  if (Date.now() - ultimaPulsacion < MARGEN_MS) return;
  vibrar(() => Haptics.selectionAsync(), 6);
}
