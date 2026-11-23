/** Petición JSON común a las dos APIs (catálogo y asistente). */

export class ErrorApi extends Error {
  constructor(
    message: string,
    readonly estado?: number,
  ) {
    super(message);
  }
}

type Opciones = {
  cuerpo?: unknown;
  signal?: AbortSignal;
  /** El asistente tarda 10-20 s con el modelo en CPU; el catálogo, milisegundos. */
  tiempoMaximoMs?: number;
  /** Nombre del servicio en los mensajes de error («la API», «el asistente»). */
  servicio?: string;
};

/** Une la cancelación de quien pide con un tiempo máximo. Devuelve la señal y cómo limpiar. */
export function senalConTiempo(signal: AbortSignal | undefined, ms: number) {
  const control = new AbortController();
  const temporizador = setTimeout(() => control.abort(), ms);
  const cancelar = () => control.abort();
  signal?.addEventListener('abort', cancelar);
  return {
    signal: control.signal,
    limpiar: () => {
      clearTimeout(temporizador);
      signal?.removeEventListener('abort', cancelar);
    },
  };
}

export async function pedirJson<T>(
  url: string,
  { cuerpo, signal, tiempoMaximoMs = 10000, servicio = 'la API' }: Opciones = {},
): Promise<T> {
  const tiempo = senalConTiempo(signal, tiempoMaximoMs);
  let respuesta: Response;
  try {
    respuesta = await fetch(url, {
      method: cuerpo === undefined ? 'GET' : 'POST',
      headers: {
        Accept: 'application/json',
        ...(cuerpo === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      signal: tiempo.signal,
    });
  } catch {
    tiempo.limpiar();
    throw new ErrorApi(`No se pudo conectar con ${servicio}`);
  }
  try {
    if (!respuesta.ok) {
      throw new ErrorApi(`${mayuscula(servicio)} respondió ${respuesta.status}`, respuesta.status);
    }
    return (await respuesta.json()) as T;
  } catch (e) {
    if (e instanceof ErrorApi) throw e;
    throw new ErrorApi(`${mayuscula(servicio)} devolvió una respuesta que no se entiende`);
  } finally {
    tiempo.limpiar();
  }
}

const mayuscula = (texto: string) => texto.charAt(0).toUpperCase() + texto.slice(1);

/** «?q=aceite&limit=50» sin los valores vacíos. */
export function consulta(parametros: Record<string, string | number | undefined | null>) {
  const partes = Object.entries(parametros)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return partes.length ? `?${partes.join('&')}` : '';
}

/** Texto para los estados de error de las pantallas que usan la API. */
export const pistaError = 'Comprueba la conexión o cambia a datos de prueba en Cuenta.';
