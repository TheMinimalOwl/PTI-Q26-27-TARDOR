import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Fonts, SinContornoWeb, Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = Omit<TextInputProps, 'style'> & { etiqueta: string; contrasena?: boolean };

export function CampoTexto({ etiqueta, contrasena, ...entrada }: Props) {
  const theme = useTheme();
  const [oculta, setOculta] = useState(true);
  const [foco, setFoco] = useState(false);

  return (
    <View style={styles.campo}>
      <ThemedText type="pieMedio">{etiqueta}</ThemedText>
      <View
        style={[
          styles.entrada,
          {
            backgroundColor: theme.backgroundElement,
            borderColor: foco ? theme.primary : 'transparent',
          },
        ]}>
        <TextInput
          {...entrada}
          accessibilityLabel={etiqueta}
          secureTextEntry={contrasena && oculta}
          placeholderTextColor={theme.textSecondary}
          onFocus={() => setFoco(true)}
          onBlur={() => setFoco(false)}
          style={[styles.texto, { color: theme.text }]}
        />
        {contrasena && (
          <Pressable
            accessibilityLabel={oculta ? 'Mostrar contraseña' : 'Ocultar contraseña'}
            hitSlop={12}
            onPress={() => setOculta((o) => !o)}>
            <Icono nombre={oculta ? 'ojo' : 'ojoTachado'} size={22} themeColor="textSecondary" />
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  campo: { gap: Spacing.one },
  entrada: {
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingHorizontal: Spacing.twelve,
    borderRadius: Radius.surface,
    borderWidth: 2,
  },
  texto: { flex: 1, fontFamily: Fonts.sans, fontSize: 17, padding: 0, ...SinContornoWeb },
});
