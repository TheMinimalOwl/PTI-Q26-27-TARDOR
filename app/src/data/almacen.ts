import { useSyncExternalStore } from 'react';
import { Platform } from 'react-native';

export type Almacen<T> = {
  get: () => T;
  set: (nuevo: T | ((actual: T) => T)) => void;
  use: () => T;
};

const hayDom = Platform.OS === 'web' && typeof window !== 'undefined';

function leer<T>(clave: string, inicial: T): T {
  if (!hayDom) return inicial;
  try {
    const guardado = window.localStorage.getItem(clave);
    return guardado == null ? inicial : (JSON.parse(guardado) as T);
  } catch {
    return inicial;
  }
}

/**
 * Estado global pequeño (tema, fuente de datos, filtros, lista) con useSyncExternalStore.
 * Con `clave`, en la web se guarda en localStorage; en el móvil no hay almacenamiento aún
 * (AsyncStorage añadiría una dependencia) y se pierde al cerrar la app.
 * En el render del servidor y en la hidratación se usa `inicial` para no desajustar el HTML.
 */
export function crearAlmacen<T>(inicial: T, clave?: string): Almacen<T> {
  let valor = clave ? leer(clave, inicial) : inicial;
  const oyentes = new Set<() => void>();

  const suscribir = (oyente: () => void) => {
    oyentes.add(oyente);
    return () => {
      oyentes.delete(oyente);
    };
  };
  const get = () => valor;

  const set: Almacen<T>['set'] = (nuevo) => {
    valor = typeof nuevo === 'function' ? (nuevo as (actual: T) => T)(valor) : nuevo;
    if (clave && hayDom) {
      try {
        window.localStorage.setItem(clave, JSON.stringify(valor));
      } catch {
        // Modo privado o cuota llena: se sigue sin guardar.
      }
    }
    oyentes.forEach((o) => o());
  };

  return {
    get,
    set,
    use: () => useSyncExternalStore(suscribir, get, () => inicial),
  };
}
