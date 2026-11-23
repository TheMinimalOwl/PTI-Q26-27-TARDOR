import { Pressable, StyleSheet, View } from 'react-native';

import { Icono, type NombreIcono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = {
  icono: NombreIcono;
  titulo: string;
  texto: string;
  accion?: { etiqueta: string; onPress: () => void };
};

/** Aviso dentro de la pantalla (error parcial, sin conexión, sin permiso). Sin color de alarma. */
export function Aviso({ icono, titulo, texto, accion }: Props) {
  const theme = useTheme();

  return (
    <View
      accessibilityRole="alert"
      style={[styles.aviso, { backgroundColor: theme.backgroundElement }]}>
      <Icono nombre={icono} size={20} />
      <View style={styles.texto}>
        <ThemedText type="cuerpo15Medio">{titulo}</ThemedText>
        <ThemedText type="pie">{texto}</ThemedText>
      </View>
      {accion && (
        <Pressable accessibilityRole="button" hitSlop={12} onPress={accion.onPress}>
          <ThemedText type="pieMedio" themeColor="link">
            {accion.etiqueta}
          </ThemedText>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  aviso: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.twelve,
    borderRadius: Radius.surface,
  },
  texto: { flex: 1 },
});
