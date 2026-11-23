import { Cadenas, type CadenaId, type SlugCadena } from '@/constants/theme';

/**
 * Datos de ejemplo de todas las pantallas, copiados de los frames de Figma (02 · Movil).
 * Es el modo «datos de prueba» (Cuenta → Precios reales). Con la API, las pantallas usan src/api.
 */

// A · Acceso

export const app = {
  nombre: 'SuperAhorro',
  frase: 'Compara el precio de tu compra en las cinco cadenas de tu barrio.',
};

export const cuenta = {
  nombre: 'Lucía Moreno',
  correo: 'lucia.moreno@correo.es',
  zona: 'Gràcia',
  tiendasFavoritas: 3,
  pie: 'SuperAhorro 1.0 · precios de 5 cadenas de Barcelona, cada mañana',
  /** Textos de segunda línea de la versión Material 3 (Android). */
  m3: {
    zona: 'Gràcia, Barcelona',
    tiendasFavoritas: ['bonarea', 'consum', 'mercadona'] as CadenaId[],
    privacidad: 'Datos de uso y permisos de ubicación',
  },
};

// B · Inicio y búsqueda

export const inicio = {
  titulo: 'Hoy en Gràcia',
  /** W1 */
  tituloWeb: 'Precios de hoy en Gràcia, Barcelona',
  hora: '8:15',
  actualizado: 'Precios de hoy, 8:15 · Barcelona',
  preguntaSugerida: '¿dónde sale más barata mi lista?',
};

export type ProductoCatalogo = {
  id: string;
  nombre: string;
  /** Texto del hueco de foto: formato del producto. */
  formato: string;
  /** Cadena con el precio por unidad más bajo. */
  cadena: SlugCadena;
  precio: number;
  precioUnidad: string;
  /** En cuántas de las 5 cadenas está. */
  cadenasCon: number;
  /** Bajada de esta semana, si la hay. */
  bajada?: number;
};

export const bajadasSemana: ProductoCatalogo[] = [
  {
    id: 'aceite',
    nombre: 'Aceite de oliva virgen extra Carbonell 1 l',
    formato: '1 l',
    cadena: 'bonarea',
    precio: 3.97,
    precioUnidad: '3,97 €/l',
    cadenasCon: 5,
    bajada: 0.41,
  },
  {
    id: 'leche',
    nombre: 'Leche semidesnatada Pascual 6 × 1 l',
    formato: '6 × 1 l',
    cadena: 'condis',
    precio: 6.54,
    precioUnidad: '1,09 €/l',
    cadenasCon: 5,
    bajada: 0.18,
  },
  {
    id: 'pollo',
    nombre: 'Pechuga de pollo fileteada 500 g',
    formato: '500 g',
    cadena: 'mercadona',
    precio: 3.48,
    precioUnidad: '6,96 €/kg',
    cadenasCon: 5,
    bajada: 0.23,
  },
];

export const busqueda = {
  consulta: 'aceite de oliva',
  resultados: [
    {
      id: 'aceite-5l',
      nombre: 'Aceite de oliva virgen extra Carbonell 5 l',
      formato: '5 l',
      cadena: 'condis',
      precio: 18.95,
      precioUnidad: '3,79 €/l',
      cadenasCon: 3,
    },
    {
      id: 'aceite',
      nombre: 'Aceite de oliva virgen extra Carbonell 1 l',
      formato: '1 l',
      cadena: 'bonarea',
      precio: 3.97,
      precioUnidad: '3,97 €/l',
      cadenasCon: 5,
    },
    {
      id: 'aceite-hacendado',
      nombre: 'Aceite de oliva virgen extra Hacendado 1 l',
      formato: '1 l',
      cadena: 'mercadona',
      precio: 4.15,
      precioUnidad: '4,15 €/l',
      cadenasCon: 1,
    },
    {
      id: 'aceite-espanola',
      nombre: 'Aceite de oliva virgen extra La Española 1 l',
      formato: '1 l',
      cadena: 'consum',
      precio: 4.49,
      precioUnidad: '4,49 €/l',
      cadenasCon: 5,
    },
    {
      id: 'aceite-coosur',
      nombre: 'Aceite de oliva virgen extra Coosur 750 ml',
      formato: '750 ml',
      cadena: 'consum',
      precio: 3.49,
      precioUnidad: '4,65 €/l',
      cadenasCon: 4,
    },
    // Más productos de ejemplo para probar la búsqueda (no salen de Figma).
    {
      id: 'leche',
      nombre: 'Leche semidesnatada Pascual 6 × 1 l',
      formato: '6 × 1 l',
      cadena: 'condis',
      precio: 6.54,
      precioUnidad: '1,09 €/l',
      cadenasCon: 5,
    },
    {
      id: 'leche-sin-lactosa',
      nombre: 'Leche sin lactosa Puleva 1 l',
      formato: '1 l',
      cadena: 'consum',
      precio: 1.29,
      precioUnidad: '1,29 €/l',
      cadenasCon: 5,
    },
    {
      id: 'leche-hacendado',
      nombre: 'Leche entera Hacendado 1 l',
      formato: '1 l',
      cadena: 'mercadona',
      precio: 0.97,
      precioUnidad: '0,97 €/l',
      cadenasCon: 1,
    },
    {
      id: 'pollo',
      nombre: 'Pechuga de pollo fileteada 500 g',
      formato: '500 g',
      cadena: 'mercadona',
      precio: 3.48,
      precioUnidad: '6,96 €/kg',
      cadenasCon: 5,
    },
    {
      id: 'arroz',
      nombre: 'Arroz redondo SOS 1 kg',
      formato: '1 kg',
      cadena: 'consum',
      precio: 1.79,
      precioUnidad: '1,79 €/kg',
      cadenasCon: 5,
    },
    {
      id: 'arroz-bomba',
      nombre: 'Arroz bomba La Fallera 1 kg',
      formato: '1 kg',
      cadena: 'bonarea',
      precio: 3.89,
      precioUnidad: '3,89 €/kg',
      cadenasCon: 4,
    },
    {
      id: 'huevos',
      nombre: 'Huevos camperos L, docena',
      formato: '12 u',
      cadena: 'mercadona',
      precio: 3.12,
      precioUnidad: '0,26 €/u',
      cadenasCon: 5,
    },
    {
      id: 'cafe',
      nombre: 'Café molido Marcilla natural 250 g',
      formato: '250 g',
      cadena: 'consum',
      precio: 3.15,
      precioUnidad: '12,60 €/kg',
      cadenasCon: 5,
    },
    {
      id: 'pasta',
      nombre: 'Espaguetis Gallo 500 g',
      formato: '500 g',
      cadena: 'mercadona',
      precio: 1.05,
      precioUnidad: '2,10 €/kg',
      cadenasCon: 5,
    },
    {
      id: 'tomate',
      nombre: 'Tomate triturado Orlando 800 g',
      formato: '800 g',
      cadena: 'caprabo',
      precio: 1.35,
      precioUnidad: '1,69 €/kg',
      cadenasCon: 5,
    },
    {
      id: 'yogur',
      nombre: 'Yogur natural Danone 4 × 120 g',
      formato: '4 u',
      cadena: 'consum',
      precio: 1.49,
      precioUnidad: '3,10 €/kg',
      cadenasCon: 5,
    },
    {
      id: 'pan',
      nombre: 'Pan de molde Bimbo sin corteza 450 g',
      formato: '450 g',
      cadena: 'bonarea',
      precio: 2.25,
      precioUnidad: '5,00 €/kg',
      cadenasCon: 5,
    },
  ] as ProductoCatalogo[],
  /** B5 */
  cargando: { texto: `Consultando precios de ${Cadenas.length} cadenas` },
};

/** B3 · Hoja de filtros */
export const filtros = {
  ordenes: ['Precio por litro o kilo', 'Precio', 'Bajada reciente'],
  ordenInicial: 'Precio por litro o kilo',
  cadenasIniciales: Cadenas.map((c) => c.id),
};

// C · Producto

export type PrecioCadena = {
  cadena: CadenaId;
  /** Sin precio: la cadena no tiene el producto. */
  precio?: number;
  precioUnidad?: string;
  tienda?: string;
  oferta?: string;
};

export type DetalleProducto = {
  id: string;
  nombreCorto: string;
  nombre: string;
  nombreCompleto: string;
  marcaFormato: string;
  formato: string;
  mejor: { cadena: CadenaId; precio: number };
  tendencia: string;
  /** Una entrada por cadena; las pantallas las muestran en el orden fijo de Cadenas. */
  precios: PrecioCadena[];
  evolucion: {
    /** Precio más barato entre las 5 cadenas, cada mes, de oct 2024 a oct 2026. */
    mensual: number[];
    primerMes: { mes: number; anio: number };
    maximo: { precio: number; mes: string };
    media2Anios: number;
    avisoBajoDe: number;
  };
};

const detalleAceite: DetalleProducto = {
  id: 'aceite',
  nombreCorto: 'Aceite',
  nombre: 'Aceite de oliva virgen extra',
  nombreCompleto: 'Aceite de oliva virgen extra Carbonell 1 l',
  marcaFormato: 'Carbonell · botella 1 l',
  formato: '1 l',
  mejor: { cadena: 'bonarea', precio: 3.97 },
  tendencia: '53 % menos que en noviembre de 2024',
  precios: [
    {
      cadena: 'bonarea',
      precio: 3.97,
      precioUnidad: '3,97 €/l',
      tienda: 'Av. Diagonal 462',
    },
    { cadena: 'consum', precio: 4.05, precioUnidad: '4,05 €/l', tienda: 'c/ Gran de Gràcia 25' },
    {
      cadena: 'condis',
      precio: 4.38,
      precioUnidad: '3,72 €/l con la oferta',
      tienda: 'Travessera de Gràcia 181',
      oferta: '2.ª unidad al 70 %',
    },
    {
      cadena: 'caprabo',
      precio: 4.45,
      precioUnidad: '4,45 €/l',
      tienda: 'A 300 m · c/ Gran de Gràcia',
    },
    { cadena: 'mercadona' },
  ],
  evolucion: {
    // Puntos de la línea de Figma (C1 y C2) pasados a euros.
    mensual: [
      8.09, 8.49, 8.28, 7.93, 7.58, 7.09, 6.84, 6.39, 5.95, 5.6, 5.35, 5.11, 4.96, 4.81, 4.7, 4.56,
      4.5, 4.39, 4.31, 4.27, 4.16, 4.11, 4.04, 4.07, 3.97,
    ],
    primerMes: { mes: 9, anio: 2024 },
    maximo: { precio: 8.49, mes: 'nov 2024' },
    media2Anios: 5.58,
    avisoBajoDe: 3.8,
  },
};

/** C3: cadena cuya web no responde en el ejemplo de error. */
export const errorPrecios = {
  cadena: 'condis' as CadenaId,
  texto: 'Su web no responde. Mostramos el resto de cadenas.',
};

export const detallesProducto: Record<string, DetalleProducto> = { aceite: detalleAceite };

// D · Preguntar

export const preguntar = {
  pregunta: '¿Dónde me sale más barata la lista de esta semana?',
  fuente: 'Precios leídos hoy a las 8:15 en la web de cada cadena.',
  sinConexion: {
    titulo: 'Sin conexión',
    texto:
      'Preguntar necesita internet. En Buscar tienes los precios guardados el 19 oct a las 21:40.',
  },
  vacio: {
    titulo: 'Pregunta por precios, tiendas o tu lista',
    texto: 'Por ejemplo, qué leche sin lactosa es más barata por litro cerca de casa.',
  },
};

// E · Lista y comparación de cesta

export type ProductoLista = {
  id: string;
  nombre: string;
  formato: string;
  /** Precio y cadena más baratos cuando se añadió. */
  precio: number;
  cadena: SlugCadena;
  cantidad: number;
};

export const listaSemana: ProductoLista[] = [
  {
    id: 'aceite',
    nombre: 'Aceite de oliva virgen extra Carbonell 1 l',
    formato: '1 l',
    precio: 3.97,
    cadena: 'bonarea',
    cantidad: 1,
  },
  {
    id: 'leche',
    nombre: 'Leche semidesnatada Pascual 6 × 1 l',
    formato: '6 × 1 l',
    precio: 6.54,
    cadena: 'condis',
    cantidad: 1,
  },
  {
    id: 'pollo',
    nombre: 'Pechuga de pollo fileteada 500 g',
    formato: '500 g',
    precio: 3.48,
    cadena: 'mercadona',
    cantidad: 1,
  },
  {
    id: 'arroz',
    nombre: 'Arroz redondo SOS 1 kg',
    formato: '1 kg',
    precio: 1.79,
    cadena: 'consum',
    cantidad: 1,
  },
  {
    id: 'huevos',
    nombre: 'Huevos camperos L, docena',
    formato: '12 u',
    precio: 3.12,
    cadena: 'mercadona',
    cantidad: 1,
  },
];

export const nombreLista = 'Lista de la semana';

/**
 * Precio de cada producto de la lista en cada cadena (tabla de W4 · Comparar cesta). Sin precio:
 * la cadena no lo tiene. Todos los totales de Inicio, Lista, Comparar y Ruta salen de aquí
 * (src/data/cesta.ts): Bonarea 19,38 €, repartida 18,90 €.
 */
export const preciosPorCadena: Record<string, Partial<Record<CadenaId, number>>> = {
  aceite: { bonarea: 3.97, consum: 4.05, condis: 4.38, caprabo: 4.45 },
  leche: { bonarea: 6.72, consum: 6.9, condis: 6.54, caprabo: 6.95 },
  pollo: {
    bonarea: 3.65,
    consum: 3.59,
    condis: 3.79,
    caprabo: 3.85,
    mercadona: 3.48,
  },
  arroz: { bonarea: 1.85, consum: 1.79, condis: 1.89, caprabo: 1.95 },
  huevos: {
    bonarea: 3.19,
    consum: 3.24,
    condis: 3.35,
    caprabo: 3.39,
    mercadona: 3.12,
  },
};

// F · Ruta de la compra

export type Coordenadas = { latitude: number; longitude: number };

export type Tienda = { direccion: string; distancia: string; coordenadas: Coordenadas };

/**
 * Tienda más cercana de cada cadena en Gràcia. Consum y Mercadona: direcciones de sus webs y
 * coordenadas de OpenStreetMap; Bonarea, Caprabo y Condis, aproximadas para el ejemplo.
 */
export const tiendas: Record<CadenaId, Tienda> = {
  bonarea: {
    direccion: 'Av. Diagonal 462',
    distancia: 'a 650 m',
    coordenadas: { latitude: 41.396188, longitude: 2.157023 },
  },
  consum: {
    direccion: 'c/ Gran de Gràcia 25',
    distancia: 'a 1,2 km',
    coordenadas: { latitude: 41.398666, longitude: 2.156728 },
  },
  condis: {
    direccion: 'Travessera de Gràcia 181',
    distancia: 'a 2,1 km',
    coordenadas: { latitude: 41.402035, longitude: 2.158718 },
  },
  caprabo: {
    direccion: 'c/ Gran de Gràcia 170',
    distancia: 'a 300 m',
    coordenadas: { latitude: 41.40205, longitude: 2.15265 },
  },
  mercadona: {
    direccion: "c/ d'Aribau 230",
    distancia: 'a 900 m',
    coordenadas: { latitude: 41.39579, longitude: 2.150309 },
  },
};

export const ruta = {
  /** En Figma solo está «A pie»; la duración en coche no está diseñada. */
  modos: ['A pie', 'En coche'] as const,
  sinPermiso: {
    titulo: 'Usa tu ubicación para trazar la ruta',
    texto:
      'Solo se usa para calcular la ruta entre las tiendas de tu lista. No se guarda tu recorrido.',
    alternativa: 'O escribe desde dónde sales',
    placeholder: 'Código postal o barrio',
  },
};

/** E3 */
export const listaVacia = {
  titulo: 'Tu lista está vacía',
  texto: 'Añade productos desde Buscar o escanea su código de barras en la tienda.',
};

// G · Cuenta y avisos

export const avisos = {
  notificaciones: {
    titulo: 'Las notificaciones están desactivadas',
    texto: 'Sin ellas los avisos solo se ven al abrir la app.',
    textoM3:
      'Sin ellas los avisos solo se ven al abrir la app. Actívalas en los ajustes de Android.',
  },
  productos: [
    {
      id: 'aceite',
      nombre: 'Aceite Carbonell',
      nombreM3: 'Aceite Carbonell 1 l',
      bajoDe: 3.8,
      activo: true,
    },
    {
      id: 'leche',
      nombre: 'Leche Pascual',
      nombreM3: 'Leche Pascual 6 × 1 l',
      bajoDe: 6.4,
      activo: true,
    },
    {
      id: 'cafe',
      nombre: 'Café Marcilla',
      nombreM3: 'Café Marcilla 250 g',
      bajoDe: 2.9,
      activo: false,
    },
  ],
  resumenLunes: false,
  resumenM3: { titulo: 'Resumen de bajadas', detalle: 'Los lunes a las 9:00' },
};

export const apariencia = {
  opciones: [
    { valor: 'auto', etiqueta: 'Automática (como el sistema)', corta: 'Automática' },
    { valor: 'light', etiqueta: 'Claro', corta: 'Claro' },
    { valor: 'dark', etiqueta: 'Oscuro', corta: 'Oscuro' },
  ] as const,
  // Figma muestra «Claro»; por defecto se sigue al sistema para no forzar el modo.
  inicial: 'auto' as 'auto' | 'light' | 'dark',
  nota: 'Automática sigue el modo claro u oscuro que tengas en el móvil.',
  m3: {
    automatica: { etiqueta: 'Automática', detalle: 'Sigue el tema oscuro de Android' },
    nota: 'Los colores de cada cadena y los precios mantienen el contraste en los dos temas.',
  },
};
