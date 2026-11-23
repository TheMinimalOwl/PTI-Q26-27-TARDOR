import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { formatoPrecio } from '@/utils/formato';
import { useTheme } from '@/hooks/use-theme';

type Props = { etiqueta: string; detalle?: string; valor: number };

/** Fila de dato: etiqueta, detalle opcional y precio a la derecha. */
export function FilaDato({ etiqueta, detalle, valor }: Props) {
  const theme = useTheme();
  return (
    <View style={[styles.fila, { borderBottomColor: theme.hairline }]}>
      <ThemedText type="cuerpo15" style={styles.etiqueta}>
        {etiqueta}
      </ThemedText>
      {detalle && <ThemedText type="pie">{detalle}</ThemedText>}
      <ThemedText type="precio15">{formatoPrecio(valor)}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  fila: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingVertical: Spacing.twelve,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  etiqueta: { flex: 1 },
});
