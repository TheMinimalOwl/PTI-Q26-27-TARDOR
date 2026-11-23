import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { MaxContentWidth, Spacing, Web } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

const REPOSITORIO = 'https://github.com/TheMinimalOwl/PTI-Q26-27-TARDOR';

type Props = {
  children: ReactNode;
  /** Columna centrada más estrecha (Preguntar: 720). */
  ancho?: number;
};

/** Página de 03 · Web a 1440: hueco del menú, columna de 1200 y pie. */
export function PaginaWeb({ children, ancho = MaxContentWidth }: Props) {
  const theme = useTheme();
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={styles.pagina}
      keyboardShouldPersistTaps="handled">
      <View style={[styles.contenido, { maxWidth: ancho + Spacing.five * 2 }]}>{children}</View>
      <View style={styles.espacio} />
      <View style={[styles.pie, { borderTopColor: theme.hairline }]}>
        <View style={styles.pieContenido}>
          <ThemedText type="pie" style={styles.flexible}>
            SuperAhorro · proyecto PTI · precios orientativos leídos cada mañana en la web de cada
            cadena
          </ThemedText>
          <EnlacePie texto="Privacidad" onPress={() => router.push('/screens/cuenta')} />
          <EnlacePie texto="Contacto" onPress={() => Linking.openURL(REPOSITORIO)} />
        </View>
      </View>
    </ScrollView>
  );
}

function EnlacePie({ texto, onPress }: { texto: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="link" onPress={onPress}>
      <ThemedText type="pie" themeColor="link" style={styles.subrayado}>
        {texto}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pagina: { flexGrow: 1, alignItems: 'center', paddingTop: Web.altoMenu },
  contenido: {
    width: '100%',
    gap: Spacing.five,
    paddingTop: 40,
    paddingBottom: Spacing.six,
    paddingHorizontal: Spacing.five,
  },
  espacio: { flex: 1, minHeight: 48 },
  pie: {
    width: '100%',
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: Spacing.four,
    paddingHorizontal: Spacing.five,
  },
  pieContenido: {
    width: '100%',
    maxWidth: MaxContentWidth,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.four,
  },
  flexible: { flex: 1 },
  subrayado: { textDecorationLine: 'underline' },
});
