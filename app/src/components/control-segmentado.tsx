import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { hapticaPulsar } from '@/utils/haptica';

type Props<T extends string> = {
  opciones: readonly T[];
  seleccionada: T;
  onCambiar: (opcion: T) => void;
};

/** Cambia entre vistas de la misma pantalla. En Android, botones segmentados de M3. */
export function ControlSegmentado<T extends string>({
  opciones,
  seleccionada,
  onCambiar,
}: Props<T>) {
  const theme = useTheme();
  const android = Platform.OS === 'android';

  return (
    <View
      accessibilityRole="tablist"
      style={[
        styles.control,
        android
          ? {
              borderWidth: 1,
              borderColor: theme.text,
              borderRadius: Radius.pill,
              padding: 0,
              gap: 0,
              overflow: 'hidden',
            }
          : { backgroundColor: theme.backgroundElement },
      ]}>
      {opciones.map((opcion) => {
        const activa = opcion === seleccionada;
        return (
          <Pressable
            key={opcion}
            accessibilityRole="tab"
            accessibilityState={{ selected: activa }}
            onPress={() => {
              hapticaPulsar();
              onCambiar(opcion);
            }}
            style={[
              styles.opcion,
              android && { borderRadius: 0 },
              activa && { backgroundColor: theme.tint },
            ]}>
            <ThemedText type="pieMedio" themeColor={activa ? 'onTint' : 'textSecondary'}>
              {opcion}
            </ThemedText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  control: {
    height: 44,
    flexDirection: 'row',
    gap: Spacing.one,
    padding: Spacing.one,
    borderRadius: Radius.surface,
  },
  opcion: { flex: 1, alignItems: 'center', justifyContent: 'center', borderRadius: Radius.surface },
});
