import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, {
  Extrapolation,
  interpolate,
  useAnimatedReaction,
  useAnimatedScrollHandler,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
} from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icono, type NombreIcono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useMargenPestanas } from '@/hooks/use-margen-pestanas';
import { useTheme } from '@/hooks/use-theme';
import { useAltoMenuWeb } from '@/hooks/use-web';

type Accion = { icono: NombreIcono; etiqueta: string; onPress: () => void };

type Props = {
  titulo: string;
  subtitulo?: string;
  accion?: Accion;
  children: ReactNode;
  /** Barra fija sobre la barra de pestañas (p. ej. el total de la lista). */
  pie?: ReactNode;
  /** Cabecera que aparece con un fundido arriba cuando el contenido pasa de `umbralFijo`. */
  fijo?: ReactNode;
  umbralFijo?: number;
};

/** Distancia de scroll en la que la cabecera fija pasa de transparente a opaca. */
const RECORRIDO_FUNDIDO = 48;

/** Pantalla raíz de pestaña: título grande de la barra de navegación y contenido con scroll. */
export function ContenedorPestana({
  titulo,
  subtitulo,
  accion,
  children,
  pie,
  fijo,
  umbralFijo = 0,
}: Props) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const margenPestanas = useMargenPestanas();
  const altoMenuWeb = useAltoMenuWeb();
  const reducirMovimiento = useReducedMotion();
  const scrollY = useSharedValue(0);
  const [fijoVisible, setFijoVisible] = useState(false);

  const onScroll = useAnimatedScrollHandler((e) => {
    scrollY.value = e.contentOffset.y;
  });

  useAnimatedReaction(
    () => scrollY.value > umbralFijo,
    (visible, anterior) => {
      if (visible !== anterior) scheduleOnRN(setFijoVisible, visible);
    },
  );

  const estiloFijo = useAnimatedStyle(() => {
    if (reducirMovimiento) return { opacity: scrollY.value > umbralFijo ? 1 : 0 };
    return {
      opacity: interpolate(
        scrollY.value,
        [umbralFijo, umbralFijo + RECORRIDO_FUNDIDO],
        [0, 1],
        Extrapolation.CLAMP,
      ),
    };
  });

  // En web el menú superior (MenuWeb) va encima del contenido.
  const paddingTop = insets.top + altoMenuWeb;
  const paddingBottom = pie ? Spacing.three : margenPestanas + Spacing.four;

  return (
    <View style={[styles.raiz, { backgroundColor: theme.background }]}>
      <Animated.ScrollView
        style={styles.raiz}
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={[styles.contenido, { paddingTop, paddingBottom }]}>
        <View style={styles.columna}>
          <View style={styles.acciones}>
            {accion && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={accion.etiqueta}
                onPress={accion.onPress}
                style={styles.accion}>
                <Icono nombre={accion.icono} />
              </Pressable>
            )}
          </View>
          <ThemedText type="display">{titulo}</ThemedText>
          {subtitulo && <ThemedText type="pie">{subtitulo}</ThemedText>}
          {children}
        </View>
      </Animated.ScrollView>

      {fijo && (
        <Animated.View
          pointerEvents={fijoVisible ? 'auto' : 'none'}
          style={[
            styles.fijo,
            {
              paddingTop: paddingTop + Spacing.two,
              // fondo/base con transparencia para que el contenido se intuya debajo
              backgroundColor: `${theme.background}F2`,
              borderBottomColor: theme.hairline,
            },
            estiloFijo,
          ]}>
          <View style={styles.columna}>{fijo}</View>
        </Animated.View>
      )}

      {pie && (
        <View
          style={[
            styles.pie,
            {
              backgroundColor: theme.surface,
              borderTopColor: theme.hairline,
              marginBottom: margenPestanas,
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
  columna: { width: '100%', maxWidth: MaxContentWidth },
  acciones: { height: 44, flexDirection: 'row', justifyContent: 'flex-end', alignItems: 'center' },
  accion: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  fijo: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
    borderBottomWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
  },
  pie: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.twelve,
    alignItems: 'center',
  },
});
