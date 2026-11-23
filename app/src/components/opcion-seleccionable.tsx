import { Pressable, StyleSheet } from 'react-native';

import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = { etiqueta: string; marcada: boolean; onPress: () => void };

/** Opción de una lista de selección (orden, cadenas), marcada con check. B3 y columna de W2. */
export function OpcionSeleccionable({ etiqueta, marcada, onPress }: Props) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: marcada }}
      onPress={onPress}
      style={[styles.opcion, { borderBottomColor: theme.hairline }]}>
      <ThemedText type="cuerpo" style={styles.espacio}>
        {etiqueta}
      </ThemedText>
      {marcada && <Icono nombre="hecho" size={22} themeColor="icon" />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  opcion: {
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  espacio: { flex: 1 },
});
