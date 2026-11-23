import { useState } from 'react';
import { Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Fonts, SinContornoWeb, Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = {
  /** Sin onChangeText es un acceso que abre la búsqueda. */
  onPress?: () => void;
  valor?: string;
  onChangeText?: (texto: string) => void;
  autoFocus?: boolean;
};

const placeholder = 'Producto, marca o código';

/** Vacío ofrece escanear; escrito ofrece borrar. En Android, píldora de M3; en web, anillo de foco. */
export function CampoBusqueda({ onPress, valor, onChangeText, autoFocus }: Props) {
  const theme = useTheme();
  const [foco, setFoco] = useState(false);
  const estilo = [
    styles.campo,
    { backgroundColor: theme.backgroundElement },
    Platform.OS === 'android' && styles.android,
    Platform.OS === 'web' && { borderColor: foco ? theme.focus : 'transparent' },
  ];

  if (!onChangeText) {
    return (
      <Pressable accessibilityRole="search" onPress={onPress} style={estilo}>
        <Icono nombre="buscar" size={20} themeColor="textSecondary" />
        <ThemedText type="cuerpo" themeColor="textSecondary" style={styles.texto} numberOfLines={1}>
          {placeholder}
        </ThemedText>
        <Icono nombre="codigo" size={22} themeColor="textSecondary" />
      </Pressable>
    );
  }

  return (
    <View style={estilo}>
      <Icono nombre="buscar" size={20} themeColor="textSecondary" />
      <TextInput
        value={valor}
        onChangeText={onChangeText}
        autoFocus={autoFocus}
        placeholder={placeholder}
        placeholderTextColor={theme.textSecondary}
        returnKeyType="search"
        accessibilityLabel="Buscar producto"
        onFocus={() => setFoco(true)}
        onBlur={() => setFoco(false)}
        style={[styles.texto, styles.entrada, { color: theme.text }]}
      />
      {valor ? (
        <Pressable accessibilityLabel="Borrar" hitSlop={12} onPress={() => onChangeText('')}>
          <Icono nombre="cerrar" size={20} themeColor="textSecondary" />
        </Pressable>
      ) : (
        <Icono nombre="codigo" size={22} themeColor="textSecondary" />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  campo: {
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingHorizontal: Spacing.twelve,
    borderRadius: Radius.surface,
    borderWidth: Platform.OS === 'web' ? 2 : 0,
    borderColor: 'transparent',
  },
  android: { borderRadius: Radius.pill, paddingHorizontal: Spacing.three },
  texto: { flex: 1 },
  entrada: { fontFamily: Fonts.sans, fontSize: 17, padding: 0, ...SinContornoWeb },
});
