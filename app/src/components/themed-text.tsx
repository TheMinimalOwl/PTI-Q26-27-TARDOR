import { StyleSheet, Text, type TextProps } from 'react-native';

import { Fonts, ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** Estilos de texto de Figma (00 · Fundamentos). */
export type ThemedTextProps = TextProps & {
  type?:
    | 'display'
    | 'titulo'
    | 'titular'
    | 'cuerpo'
    | 'cuerpo15'
    | 'cuerpo15Medio'
    | 'pie'
    | 'pieMedio'
    | 'etiqueta'
    | 'nota'
    | 'precio34'
    | 'precio22'
    | 'precio17'
    | 'precio15'
    | 'enlace';
  themeColor?: ThemeColor;
};

const defaultColor: Partial<Record<NonNullable<ThemedTextProps['type']>, ThemeColor>> = {
  display: 'title',
  titulo: 'title',
  pie: 'textSecondary',
  nota: 'textSecondary',
  etiqueta: 'textSecondary',
  precio34: 'title',
  precio22: 'title',
  enlace: 'link',
};

export function ThemedText({ style, type = 'cuerpo', themeColor, ...rest }: ThemedTextProps) {
  const theme = useTheme();
  const color = theme[themeColor ?? defaultColor[type] ?? 'text'];

  return <Text style={[{ color }, styles[type], style]} {...rest} />;
}

const display = { fontFamily: Fonts.serif, fontSize: 34, lineHeight: 40 };
const titulo = { fontFamily: Fonts.serif, fontSize: 22, lineHeight: 28 };
const cuerpo = { fontFamily: Fonts.sans, fontSize: 17, lineHeight: 24 };
const cuerpo15 = { fontFamily: Fonts.sans, fontSize: 15, lineHeight: 21 };
const pie = { fontFamily: Fonts.sans, fontSize: 13, lineHeight: 18 };
const pieMedio = { fontFamily: Fonts.sansMedium, fontSize: 13, lineHeight: 18 };

const styles = StyleSheet.create({
  display,
  titulo,
  titular: { fontFamily: Fonts.sansSemiBold, fontSize: 17, lineHeight: 22 },
  cuerpo,
  cuerpo15,
  cuerpo15Medio: { fontFamily: Fonts.sansMedium, fontSize: 15, lineHeight: 21 },
  pie,
  pieMedio,
  etiqueta: {
    fontFamily: Fonts.sansSemiBold,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  nota: { fontFamily: Fonts.sansMedium, fontSize: 11, lineHeight: 14 },
  precio34: {
    fontFamily: Fonts.sansSemiBold,
    fontSize: 34,
    lineHeight: 40,
    letterSpacing: -1,
    fontVariant: ['tabular-nums'],
  },
  precio22: {
    fontFamily: Fonts.sansSemiBold,
    fontSize: 22,
    lineHeight: 28,
    fontVariant: ['tabular-nums'],
  },
  precio17: {
    fontFamily: Fonts.sansSemiBold,
    fontSize: 17,
    lineHeight: 22,
    fontVariant: ['tabular-nums'],
  },
  precio15: {
    fontFamily: Fonts.sansMedium,
    fontSize: 15,
    lineHeight: 21,
    fontVariant: ['tabular-nums'],
  },
  enlace: { fontFamily: Fonts.sansMedium, fontSize: 17, lineHeight: 24 },
});
