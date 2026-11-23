import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** Tablas de 03 · Web: filas con separador fino, sin tarjetas. */

type PropsFila = {
  children: ReactNode;
  /** Fila con enlace: cambia de fondo con el ratón encima (estado/pulsado). */
  onPress?: () => void;
  etiqueta?: string;
  /** Fila de totales: línea superior marcada. */
  total?: boolean;
  /** Fila resaltada en tinte paja (la mejor opción). */
  mejor?: boolean;
  /** Fila de títulos de columna. */
  cabecera?: boolean;
};

export function FilaTabla({ children, onPress, etiqueta, total, mejor, cabecera }: PropsFila) {
  const theme = useTheme();
  const base: StyleProp<ViewStyle> = [
    styles.fila,
    total
      ? { borderTopWidth: 1, borderTopColor: theme.text, borderBottomWidth: 0 }
      : { borderBottomColor: theme.hairline },
    mejor && { backgroundColor: theme.tint },
    cabecera && styles.filaCabecera,
  ];

  if (!onPress) return <View style={base}>{children}</View>;
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={etiqueta}
      onPress={onPress}
      style={(estado) => [
        base,
        (estado as { hovered?: boolean }).hovered && !mejor && { backgroundColor: theme.hover },
      ]}>
      {children}
    </Pressable>
  );
}

type PropsCelda = {
  children?: ReactNode;
  /** Ancho fijo; sin él la celda ocupa el espacio que sobra. */
  ancho?: number;
  derecha?: boolean;
  /** Celda más barata de la fila o columna: tinte paja. */
  mejor?: boolean;
  /** Celda de cabecera: algo menos de alto. */
  cabecera?: boolean;
  /** Margen lateral de 8 en vez de 12 (columnas de cadena estrechas). */
  estrecha?: boolean;
};

export function Celda({ children, ancho, derecha, mejor, cabecera, estrecha }: PropsCelda) {
  const theme = useTheme();
  return (
    <View
      style={[
        styles.celda,
        ancho ? { width: ancho } : styles.flexible,
        derecha && styles.derecha,
        cabecera && styles.cabecera,
        estrecha && styles.estrecha,
        mejor && { backgroundColor: theme.tint },
      ]}>
      {children}
    </View>
  );
}

/** Texto de cabecera de columna (Pie/13 Medio, secundario). */
export function TituloColumna({ children }: { children: string }) {
  return (
    <ThemedText type="pieMedio" themeColor="textSecondary" numberOfLines={1}>
      {children}
    </ThemedText>
  );
}

/** Precio de una celda: «—» si no hay; sobre tinte, en color sobre-tinte. */
export function PrecioCelda({ texto, mejor }: { texto?: string; mejor?: boolean }) {
  return (
    <ThemedText type="precio15" themeColor={mejor ? 'onTint' : texto ? 'text' : 'textSecondary'}>
      {texto ?? '—'}
    </ThemedText>
  );
}

const styles = StyleSheet.create({
  fila: { flexDirection: 'row', minHeight: 56, borderBottomWidth: StyleSheet.hairlineWidth },
  filaCabecera: { minHeight: 0 },
  celda: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingHorizontal: Spacing.twelve,
    paddingVertical: Spacing.two,
  },
  flexible: { flex: 1, minWidth: 0 },
  derecha: { justifyContent: 'flex-end' },
  cabecera: { paddingVertical: 10 },
  estrecha: { paddingHorizontal: Spacing.two },
});
