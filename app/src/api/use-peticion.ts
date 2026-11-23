import { useCallback, useEffect, useState } from 'react';

export type Peticion<T> =
  | { estado: 'cargando' }
  | { estado: 'ok'; datos: T }
  | { estado: 'error'; mensaje: string };

/** Lo que devuelve usePeticion: el estado más `reintentar`. */
export type EstadoPeticion<T> = Peticion<T> & { reintentar: () => void };

const CARGANDO = { estado: 'cargando' } as const;

/**
 * Lanza `pedir` cuando cambian `claves` y cancela la petición anterior. Con `activa` a false no
 * pide nada (p. ej. en modo datos de prueba). `espera` retrasa la petición (búsqueda al escribir).
 * Mientras la respuesta guardada sea de otras claves, el estado es «cargando».
 */
export function usePeticion<T>(
  pedir: (signal: AbortSignal) => Promise<T>,
  claves: unknown[],
  { activa = true, espera = 0 }: { activa?: boolean; espera?: number } = {},
): EstadoPeticion<T> {
  const [intento, setIntento] = useState(0);
  const clave = JSON.stringify([...claves, intento]);
  const [respuesta, setRespuesta] = useState<{ clave: string; valor: Peticion<T> } | null>(null);

  useEffect(() => {
    if (!activa) return;
    const control = new AbortController();
    const t = setTimeout(() => {
      pedir(control.signal).then(
        (datos) => {
          if (!control.signal.aborted) setRespuesta({ clave, valor: { estado: 'ok', datos } });
        },
        (e: Error) => {
          if (!control.signal.aborted)
            setRespuesta({ clave, valor: { estado: 'error', mensaje: e.message } });
        },
      );
    }, espera);
    return () => {
      clearTimeout(t);
      control.abort();
    };
    // `pedir` cambia en cada render; lo que decide repetir la petición es `clave`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activa, clave, espera]);

  const reintentar = useCallback(() => setIntento((i) => i + 1), []);
  const valor: Peticion<T> = respuesta?.clave === clave ? respuesta.valor : CARGANDO;
  return { ...valor, reintentar };
}
