import { StyleSheet, View } from 'react-native';

import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** Fila de producto en carga: bloques estáticos, sin animación en bucle. */
export function FilaCargando() {
  const theme = useTheme();
  const bloque = { backgroundColor: theme.backgroundSelected };

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.fila, { borderBottomColor: theme.hairline }]}>
      <View style={[styles.foto, bloque]} />
      <View style={styles.info}>
        <View style={[styles.linea, styles.larga, bloque]} />
        <View style={[styles.linea, styles.corta, bloque]} />
      </View>
      <View style={[styles.linea, styles.precio, bloque]} />
    </View>
  );
}

const styles = StyleSheet.create({
  fila: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    paddingVertical: Spacing.twelve,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  foto: { width: 64, height: 64, borderRadius: 8 },
  info: { flex: 1, gap: Spacing.two },
  linea: { height: 14, borderRadius: Radius.pill },
  larga: { width: '100%' },
  corta: { width: '60%' },
  precio: { width: 56, height: 16 },
});
