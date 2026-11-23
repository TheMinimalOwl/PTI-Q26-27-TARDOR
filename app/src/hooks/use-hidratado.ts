import { useSyncExternalStore } from 'react';

const sinSuscripcion = () => () => {};

/**
 * false en el render del servidor y en la hidratación de la web; true después (y siempre en el
 * móvil). Lo que dependa del navegador (ancho, modo oscuro del sistema) debe esperar a esto para
 * que el primer render del cliente coincida con el HTML del servidor.
 */
export function useHidratado() {
  return useSyncExternalStore(
    sinSuscripcion,
    () => true,
    () => false,
  );
}
