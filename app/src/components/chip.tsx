import { Platform, Pressable, StyleSheet } from 'react-native';

import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { hapticaPulsar } from '@/utils/haptica';

type Props = {
  etiqueta: string;
  /** Activo: filtro aplicado, se quita con la x. Inactivo: filtro desplegable. */
  activo?: boolean;
  onPress: () => void;
};

export function Chip({ etiqueta, activo, onPress }: Props) {
  const theme = useTheme();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={activo ? `Quitar filtro ${etiqueta}` : etiqueta}
      hitSlop={{ top: 6, bottom: 6 }}
      onPress={() => {
        hapticaPulsar();
        onPress();
      }}
      style={[
        styles.chip,
        activo ? { backgroundColor: theme.tint } : { borderWidth: 1, borderColor: theme.hairline },
        // M3: filter chip con esquinas de 8
        Platform.OS === 'android' && { borderRadius: 8 },
      ]}>
      <ThemedText type="pieMedio" themeColor={activo ? 'onTint' : 'text'}>
        {etiqueta}
      </ThemedText>
      <Icono
        nombre={activo ? 'cerrar' : 'desplegar'}
        size={16}
        themeColor={activo ? 'onTint' : 'text'}
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    height: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.one,
    paddingLeft: Spacing.twelve,
    paddingRight: Spacing.two,
    borderRadius: Radius.pill,
  },
});
