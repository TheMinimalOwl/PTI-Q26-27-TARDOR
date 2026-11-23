import type { ReactNode } from 'react';
import { ScrollView, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useAltoMenuWeb } from '@/hooks/use-web';

type Props = {
  children: ReactNode;
  /** Barra fija abajo (acción principal o total). */
  pie?: ReactNode;
  /** El contenido ocupa al menos toda la altura (para empujar acciones abajo con un espacio flexible). */
  llenar?: boolean;
  /** Pantallas sin barra de navegación: deja sitio a la barra de estado. */
  sinCabecera?: boolean;
  estiloContenido?: StyleProp<ViewStyle>;
};

/** Pantalla fuera de pestañas: la barra superior la pinta el Stack nativo (iOS o M3); en la web, MenuWeb. */
export function PantallaDetalle({ children, pie, llenar, sinCabecera, estiloContenido }: Props) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const altoMenuWeb = useAltoMenuWeb();

  return (
    <View style={[styles.raiz, { backgroundColor: theme.background }]}>
      <ScrollView
        style={styles.raiz}
        keyboardShouldPersistTaps="handled"
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={[
          styles.contenido,
          llenar && styles.llenar,
          {
            // En la web no hay barra de navegación por pantalla: el contenido va bajo el menú.
            paddingTop: (sinCabecera ? insets.top : Spacing.two) + altoMenuWeb,
            paddingBottom: (pie ? 0 : insets.bottom) + Spacing.three,
          },
        ]}>
        <View style={[styles.columna, llenar && styles.llenar, estiloContenido]}>{children}</View>
      </ScrollView>
      {pie && (
        <View
          style={[
            styles.pie,
            {
              backgroundColor: theme.surface,
              borderTopColor: theme.hairline,
              paddingBottom: insets.bottom + Spacing.twelve,
            },
          ]}>
          <View style={styles.columna}>{pie}</View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  raiz: { flex: 1 },
  contenido: { paddingHorizontal: Spacing.three, alignItems: 'center' },
  llenar: { flexGrow: 1 },
  columna: { width: '100%', maxWidth: MaxContentWidth, gap: Spacing.three },
  pie: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: Spacing.three,
    paddingTop: Spacing.twelve,
    alignItems: 'center',
  },
});
