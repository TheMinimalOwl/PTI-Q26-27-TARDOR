import { Pressable, StyleSheet, View } from 'react-native';

import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Radius } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { hapticaPulsar } from '@/utils/haptica';

type Props = { cantidad: number; onCambiar: (cantidad: number) => void };

/** Con 1 unidad, quitar pasa a papelera y borra el producto (cantidad 0). */
export function SelectorCantidad({ cantidad, onCambiar }: Props) {
  const theme = useTheme();

  return (
    <View style={[styles.pildora, { backgroundColor: theme.backgroundElement }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={cantidad === 1 ? 'Quitar de la lista' : 'Una unidad menos'}
        hitSlop={{ top: 6, bottom: 6 }}
        onPress={() => {
          hapticaPulsar();
          onCambiar(cantidad - 1);
        }}
        style={styles.boton}>
        <Icono nombre={cantidad === 1 ? 'papelera' : 'menos'} size={18} />
      </Pressable>
      <ThemedText type="precio15" style={styles.cantidad}>
        {cantidad}
      </ThemedText>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Una unidad más"
        hitSlop={{ top: 6, bottom: 6 }}
        onPress={() => {
          hapticaPulsar();
          onCambiar(cantidad + 1);
        }}
        style={styles.boton}>
        <Icono nombre="mas" size={18} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  pildora: { height: 36, flexDirection: 'row', alignItems: 'center', borderRadius: Radius.pill },
  boton: { width: 40, height: 36, alignItems: 'center', justifyContent: 'center' },
  cantidad: { width: 20, textAlign: 'center' },
});
