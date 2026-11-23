/**
 * Cliente del asistente (pti-repo, rama `ai`: flujo-ia/rag/serve.py; contrato en
 * flujo-ia/docs/06-integracion-api.md y rag/schemas/respuesta-asistente.schema.json).
 * Usa `/ask/stream` para pintar la respuesta según llega y cae a `/ask` si no hay streaming.
 */
import { fetch as fetchExpo } from 'expo/fetch';

import { ErrorApi, pedirJson, senalConTiempo } from '@/api/http';

/** Para probar en local: EXPO_PUBLIC_RAG_URL=http://<ip-del-pc>:8080 */
export const RAG_URL = (process.env.EXPO_PUBLIC_RAG_URL ?? 'https://rag.superahorro.app').replace(
  /\/$/,
  '',
);

/** Con el modelo de 8B en CPU una respuesta tarda 9-16 s. */
const TIEMPO_MAXIMO_MS = 60000;
const SERVICIO = 'el asistente';

export type FuenteRespuesta = {
  id: string;
  nombre: string;
  cadena: string;
  precio: number | null;
  precioUnidad: number | null;
  unidad: string | null;
  url: string | null;
};

export type Respuesta = {
  /** Texto sin las citas [id]: las fuentes van debajo como filas. */
  texto: string;
  fuentes: FuenteRespuesta[];
  /** El asistente no encontró la respuesta en los datos: se pinta como aviso, no como error. */
  abstenida: boolean;
  avisos: string[];
};

// Contrato de /ask
type RagFuente = {
  id: string;
  name: string;
  chain: string;
  price_total: number | null;
  price_unit: number | null;
  unit: string | null;
  url: string | null;
};
type RagRespuesta = {
  answer: string;
  sources: RagFuente[];
  abstained: boolean;
  guardrails: { ok: boolean; warnings: string[] };
};

// Evento `fin` de /ask/stream. Ojo: aquí los importes llegan como texto («3.39»), no como número.
type RagHit = {
  id: string;
  name: string;
  chain: string;
  total: number | string | null;
  unit_price: number | string | null;
  unit: string | null;
  url: string | null;
};
type RagFin = {
  respuesta: string;
  hits: RagHit[];
  abstained: boolean;
  guardrails: { ok: boolean; warnings: string[] };
};

/** Importe del asistente → número; null si falta o no es un número. */
const aNumero = (v: number | string | null | undefined) => {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const CITA = /\s?\[[^\]\s]+\]/g;
export const sinCitas = (texto: string) => texto.replace(CITA, '').trim();
const citados = (texto: string) =>
  new Set([...texto.matchAll(/\[([^\]\s]+)\]/g)].map((m) => m[1]));

function desdeAsk(r: RagRespuesta): Respuesta {
  return {
    texto: sinCitas(r.answer),
    abstenida: r.abstained,
    avisos: r.guardrails.ok ? [] : r.guardrails.warnings,
    fuentes: r.sources.map((s) => ({
      id: s.id,
      nombre: s.name,
      cadena: s.chain,
      precio: aNumero(s.price_total),
      precioUnidad: aNumero(s.price_unit),
      unidad: s.unit,
      url: s.url,
    })),
  };
}

/** En el streaming las fuentes son los productos del contexto que la respuesta cita. */
function desdeFin(f: RagFin): Respuesta {
  const ids = citados(f.respuesta);
  return {
    texto: sinCitas(f.respuesta),
    abstenida: f.abstained,
    avisos: f.guardrails.ok ? [] : f.guardrails.warnings,
    fuentes: f.hits
      .filter((h) => ids.has(String(h.id)))
      .map((h) => ({
        id: String(h.id),
        nombre: h.name,
        cadena: h.chain,
        precio: aNumero(h.total),
        precioUnidad: aNumero(h.unit_price),
        unidad: h.unit,
        url: h.url,
      })),
  };
}

/** Producto equivalente en otra cadena según `/equiv` (los ids son los de la API de catálogo). */
export type Equivalente = {
  id: string;
  nombre: string;
  cadena: string;
  precio: number | null;
  precioUnidad: number | null;
  unidad: string | null;
  /** 0-1: lo seguro que está el asistente de que es el mismo producto. */
  confianza: number;
};

type RagEquiv = {
  elegido: (RagHit & { id: string | number }) | null;
  confianza: number | null;
};

export const rag = {
  /**
   * El mismo producto (o el más parecido) en `cadena`, elegido por el asistente con el LLM.
   * null si no lo encuentra.
   */
  equivalente: async (id: string, cadena: string, signal?: AbortSignal): Promise<Equivalente | null> => {
    const r = await pedirJson<RagEquiv>(`${RAG_URL}/equiv`, {
      cuerpo: { id, chain: cadena },
      signal,
      tiempoMaximoMs: TIEMPO_MAXIMO_MS,
      servicio: SERVICIO,
    });
    const e = r.elegido;
    if (!e) return null;
    return {
      id: String(e.id),
      nombre: e.name,
      cadena: e.chain,
      precio: aNumero(e.total),
      precioUnidad: aNumero(e.unit_price),
      unidad: e.unit,
      confianza: r.confianza ?? 0,
    };
  },

  /** Comprueba que el servicio responde (Preguntar muestra «Sin conexión» si no). */
  salud: (signal?: AbortSignal) =>
    pedirJson<{ ok: boolean }>(`${RAG_URL}/health`, { signal, servicio: SERVICIO }),

  preguntar: async (question: string, signal?: AbortSignal) =>
    desdeAsk(
      await pedirJson<RagRespuesta>(`${RAG_URL}/ask`, {
        cuerpo: { question },
        signal,
        tiempoMaximoMs: TIEMPO_MAXIMO_MS,
        servicio: SERVICIO,
      }),
    ),

  /**
   * Respuesta token a token. `alTexto` recibe el texto acumulado (sin citas). Si el servicio no
   * tiene LLM (400) o el cliente no puede leer el flujo antes del primer token, usa `/ask`.
   */
  preguntarEnVivo: async (
    question: string,
    alTexto: (texto: string) => void,
    signal?: AbortSignal,
  ): Promise<Respuesta> => {
    const tiempo = senalConTiempo(signal, TIEMPO_MAXIMO_MS);
    let acumulado = '';
    try {
      // expo/fetch lee el cuerpo como flujo también en Android e iOS.
      const r = await fetchExpo(`${RAG_URL}/ask/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ question }),
        signal: tiempo.signal,
      });
      if (!r.ok || !r.body) throw new ErrorApi('sin streaming', r.status);

      const lector = r.body.getReader();
      const decodificador = new TextDecoder();
      let pendiente = '';
      for (;;) {
        const { value, done } = await lector.read();
        if (done) break;
        pendiente += decodificador.decode(value, { stream: true });
        const bloques = pendiente.split('\n\n');
        pendiente = bloques.pop() ?? '';
        for (const bloque of bloques) {
          const evento = /^event: (.*)$/m.exec(bloque)?.[1];
          const datos = /^data: (.*)$/m.exec(bloque)?.[1];
          if (!evento || datos === undefined) continue;
          const valor = JSON.parse(datos);
          if (evento === 'token') {
            acumulado += valor as string;
            alTexto(sinCitas(acumulado));
          } else if (evento === 'fin') {
            return desdeFin(valor as RagFin);
          } else if (evento === 'error') {
            throw new ErrorApi((valor as { error: string }).error);
          }
        }
      }
      throw new ErrorApi(`${SERVICIO} cortó la respuesta`);
    } catch (e) {
      if (signal?.aborted) throw e;
      // Sin nada pintado aún, se pide la respuesta completa; si ya había texto, es un error real.
      if (acumulado === '') return rag.preguntar(question, signal);
      throw e instanceof ErrorApi ? e : new ErrorApi(`Se perdió la conexión con ${SERVICIO}`);
    } finally {
      tiempo.limpiar();
    }
  },
};
