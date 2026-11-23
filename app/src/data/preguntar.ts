import { useEffect, useRef, useState } from 'react';

import { rag, type Respuesta } from '@/api/rag';
import { usePeticion } from '@/api/use-peticion';
import { useModoApi } from '@/data/fuente-datos';

export type Mensaje = {
  id: number;
  pregunta: string;
  estado: 'esperando' | 'ok' | 'error';
  /** Texto que va llegando por streaming antes de la respuesta completa. */
  parcial: string;
  respuesta?: Respuesta;
  error?: string;
};

/** En modo prueba no hay asistente: se explica en vez de inventar una respuesta. */
const respuestaDePrueba: Respuesta = {
  texto:
    'Con datos de prueba el asistente no contesta preguntas nuevas. Activa «Precios reales (API)» en Cuenta para preguntar al asistente.',
  fuentes: [],
  abstenida: true,
  avisos: [],
};

/**
 * Conversación de D1/W5 con el asistente (RAG). `sinConexion` es D2: el asistente no responde a
 * `/health` o se fuerza con `?sinConexion=1`.
 */
export function usePreguntar(forzarSinConexion = false) {
  const modoApi = useModoApi();
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [forzada, setForzada] = useState(forzarSinConexion);
  const salud = usePeticion((signal) => rag.salud(signal), [], { activa: modoApi && !forzada });
  const controles = useRef(new Set<AbortController>());
  const siguienteId = useRef(0);

  // Al salir de la pantalla se cancelan las respuestas a medias.
  useEffect(() => {
    const activos = controles.current;
    return () => activos.forEach((c) => c.abort());
  }, []);

  const sinConexion = forzada || (modoApi && salud.estado === 'error');

  const actualizar = (id: number, cambio: Partial<Mensaje>) =>
    setMensajes((ms) => ms.map((m) => (m.id === id ? { ...m, ...cambio } : m)));

  const enviar = async (pregunta: string) => {
    const texto = pregunta.trim();
    if (!texto || sinConexion) return;
    const id = siguienteId.current++;
    setMensajes((ms) => [...ms, { id, pregunta: texto, estado: 'esperando', parcial: '' }]);

    if (!modoApi) {
      actualizar(id, { estado: 'ok', respuesta: respuestaDePrueba });
      return;
    }
    const control = new AbortController();
    controles.current.add(control);
    try {
      const respuesta = await rag.preguntarEnVivo(
        texto,
        (parcial) => actualizar(id, { parcial }),
        control.signal,
      );
      actualizar(id, { estado: 'ok', respuesta });
    } catch (e) {
      if (!control.signal.aborted) {
        actualizar(id, { estado: 'error', error: (e as Error).message });
      }
    } finally {
      controles.current.delete(control);
    }
  };

  const reintentarConexion = () => {
    setForzada(false);
    salud.reintentar();
  };

  return {
    mensajes,
    enviar,
    ocupado: mensajes.some((m) => m.estado === 'esperando'),
    sinConexion,
    reintentarConexion,
    /** En modo prueba se enseña la conversación de ejemplo de Figma antes de la primera pregunta. */
    conEjemplo: !modoApi,
  };
}
