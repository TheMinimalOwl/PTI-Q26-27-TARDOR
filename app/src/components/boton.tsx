import { Platform, Pressable, StyleSheet, type StyleProp, type ViewStyle } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { hapticaPulsar } from '@/utils/haptica';

type Props = {
  etiqueta: string;
  onPress: () => void;
  /** Primario: la acción principal de la pantalla (máximo uno). El resto son secundarias. */
  tipo?: 'primario' | 'secundario' | 'texto' | 'textoNeutro';
  deshabilitado?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Boton({ etiqueta, onPress, tipo = 'primario', deshabilitado, style }: Props) {
  const theme = useTheme();
  const primario = tipo === 'primario';
  const colorTexto = {
    primario: theme.onPrimary,
    secundario: theme.text,
    texto: theme.link,
    textoNeutro: theme.textSecondary,
  }[tipo];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: deshabilitado }}
      disabled={deshabilitado}
      onPress={() => {
        hapticaPulsar();
        onPress();
      }}
      style={({ pressed }) => [
        styles.boton,
        primario && { backgroundColor: theme.primary, paddingHorizontal: Spacing.twenty },
        tipo === 'secundario' && {
          borderWidth: 1,
          borderColor: theme.hairline,
          paddingHorizontal: Spacing.twenty,
        },
        { opacity: deshabilitado ? 0.4 : pressed ? 0.85 : 1 },
        Platform.OS === 'android' && { borderRadius: Radius.pill },
        style,
      ]}>
      <ThemedText type="titular" numberOfLines={1} style={{ color: colorTexto }}>
        {etiqueta}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  boton: {
    height: 48,
    paddingHorizontal: Spacing.twelve,
    borderRadius: Radius.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
