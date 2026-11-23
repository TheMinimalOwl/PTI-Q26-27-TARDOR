/**
 * Tokens de SuperAhorro, copiados de las variables "SA · Color" y "SA · Espaciado" de Figma
 * (exportadas en superahorro-tokens.json). Si cambian en Figma, se actualizan aquí.
 */

import '@/global.css';

import { Platform, type TextStyle } from 'react-native';

export const Colors = {
  light: {
    // Nombres que usan los componentes de la plantilla de Expo
    text: '#1E2219', // texto/principal
    textSecondary: '#5A5F4E', // texto/secundario
    background: '#F6F4E8', // fondo/base
    backgroundElement: '#EDEBDA', // fondo/superficie-2
    backgroundSelected: '#E3E1C9', // fondo/superficie-3
    // Resto de tokens de SuperAhorro
    surface: '#FDFCF7', // fondo/superficie
    title: '#2F3A27', // texto/titulo
    hairline: '#DEDBC4', // borde/hairline
    primary: '#6A795D', // accion/primaria
    onPrimary: '#FFFFFF', // accion/sobre-primaria
    link: '#4E5B43', // accion/enlace
    icon: '#6A795D', // accion/icono
    tint: '#EFEBC4', // estado/tinte
    onTint: '#3A4130', // estado/sobre-tinte
    down: '#4E6B3A', // estado/bajada
    up: '#9A4A2E', // estado/subida
    hover: '#1E22190F', // estado/pulsado (fila con el ratón encima en la web)
    focus: '#4E5B43', // estado/foco (anillo de teclado)
  },
  dark: {
    text: '#ECEADB',
    textSecondary: '#B3B4A0',
    background: '#141611',
    backgroundElement: '#252920',
    backgroundSelected: '#2F3428',
    surface: '#1C1F18',
    title: '#F2EFD8',
    hairline: '#363B2E',
    primary: '#B2BD7E',
    onPrimary: '#1E2419',
    link: '#D9D28B',
    icon: '#B2BD7E',
    tint: '#D9D28B24',
    onTint: '#E6E0A6',
    down: '#A9C78F',
    up: '#E39A80',
    hover: '#ECEADB14',
    focus: '#D9D28B',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

/**
 * Colores de marca (SA · Color / marca-*). Solo se usan en el punto de 8 px junto al nombre.
 * Bonarea y Condis no están aún en Figma: tonos apagados como el resto, con su versión oscura.
 */
export const Marcas = {
  light: {
    bonarea: '#4F6E23',
    caprabo: '#9E2E3C',
    condis: '#A4432A',
    consum: '#955F32',
    mercadona: '#1A5A3A',
  },
  dark: {
    bonarea: '#A9C47E',
    caprabo: '#D6959B',
    condis: '#E3A08C',
    consum: '#CDA175',
    mercadona: '#6EA988',
  },
} as const;

export type CadenaId = keyof typeof Marcas.light;

/** Slug de cadena tal y como llega de la API: una de las 5 o una que la app aún no conoce. */
export type SlugCadena = CadenaId | (string & {});

/** Color del punto de marca; neutro (null) para una cadena desconocida. */
export const colorMarca = (id: SlugCadena, esquema: 'light' | 'dark'): string | null =>
  (Marcas[esquema] as Record<string, string>)[id] ?? null;

/** Las cadenas que tiene la API de catálogo (`GET /chains`), en el orden fijo del proyecto. */
export const Cadenas: { id: CadenaId; nombre: string }[] = [
  { id: 'bonarea', nombre: 'Bonarea' },
  { id: 'caprabo', nombre: 'Caprabo' },
  { id: 'condis', nombre: 'Condis' },
  { id: 'consum', nombre: 'Consum' },
  { id: 'mercadona', nombre: 'Mercadona' },
];

/**
 * Familias cargadas en src/app/_layout.tsx con useFonts. En Android cada peso es una familia
 * distinta, así que no se combina fontFamily con fontWeight.
 */
export const Fonts = {
  serif: 'SourceSerif4-Medium',
  sans: 'SourceSans3-Regular',
  sansMedium: 'SourceSans3-Medium',
  sansSemiBold: 'SourceSans3-SemiBold',
} as const;

/** Escala de SA · Espaciado (4–64). */
export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  twelve: 12,
  three: 16,
  twenty: 20,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const Radius = {
  surface: 10,
  pill: 999,
} as const;

/** Alto de la barra de pestañas de iOS. Úsalo con useMargenPestanas(). */
export const BottomTabInset = 50;
export const MaxContentWidth = 1200;

/** Web (03 · Web): menú superior y a partir de qué ancho se usa la maqueta de escritorio. */
export const Web = {
  altoMenu: 72,
  altoMenuEstrecho: 56,
  anchoEscritorio: 900,
  /** Columna de lectura de Preguntar (W5). */
  anchoLectura: 720,
} as const;

/** Campos de texto en la web: sin el contorno del navegador, porque ya tienen su anillo de foco. */
// react-native-web acepta 'none' aunque los tipos de RN solo listan solid, dotted y dashed.
export const SinContornoWeb = (Platform.OS === 'web' ? { outlineStyle: 'none' } : {}) as TextStyle;
