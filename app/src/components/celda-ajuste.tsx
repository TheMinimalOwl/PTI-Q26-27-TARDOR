import type { ReactNode } from 'react';
import { Platform, Pressable, StyleSheet, Switch, View } from 'react-native';

import { Icono, type NombreIcono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { hapticaPulsar } from '@/utils/haptica';

type Props = {
  etiqueta: string;
  icono?: NombreIcono;
  detalle?: string;
  /** Segunda línea bajo la etiqueta (filas de dos líneas de M3). */
  subtitulo?: string;
  /** Con `activado` la celda lleva un interruptor nativo. */
  activado?: boolean;
  onCambiar?: (valor: boolean) => void;
  /** Sin interruptor: la celda navega y muestra un chevron. */
  onPress?: () => void;
  derecha?: ReactNode;
  /** Dentro de un GrupoAjustes: fondo de superficie y margen interior. */
  enGrupo?: boolean;
};

/** Fila de ajustes de 52 de alto. El interruptor es el Switch del sistema con trackColor accion/primaria. */
export function CeldaAjuste({
  etiqueta,
  icono,
  detalle,
  subtitulo,
  activado,
  onCambiar,
  onPress,
  derecha,
  enGrupo,
}: Props) {
  const theme = useTheme();
  const conInterruptor = activado !== undefined;

  const contenido = (
    <>
      {icono && <Icono nombre={icono} size={22} />}
      <View style={styles.texto}>
        <ThemedText type="cuerpo" numberOfLines={1}>
          {etiqueta}
        </ThemedText>
        {subtitulo && <ThemedText type="pie">{subtitulo}</ThemedText>}
      </View>
      {detalle && (
        <ThemedText type="cuerpo15" themeColor="textSecondary">
          {detalle}
        </ThemedText>
      )}
      {derecha}
      {conInterruptor ? (
        <Switch
          accessibilityLabel={etiqueta}
          value={activado}
          onValueChange={(v) => {
            hapticaPulsar();
            onCambiar?.(v);
          }}
          trackColor={{ true: theme.primary, false: theme.backgroundSelected }}
          // En Android el círculo apagado debe contrastar con el fondo también en oscuro.
          thumbColor={
            Platform.OS === 'android'
              ? activado
                ? theme.onPrimary
                : theme.textSecondary
              : undefined
          }
          ios_backgroundColor={theme.backgroundSelected}
        />
      ) : (
        onPress && <Icono nombre="siguiente" size={20} themeColor="textSecondary" />
      )}
    </>
  );

  const estilo = [
    styles.celda,
    { borderBottomColor: theme.hairline },
    enGrupo && { backgroundColor: theme.surface, paddingHorizontal: Spacing.three },
    subtitulo !== undefined && styles.dosLineas,
  ];

  return onPress && !conInterruptor ? (
    <Pressable
      accessibilityRole="button"
      onPress={() => {
        hapticaPulsar();
        onPress();
      }}
      style={estilo}>
      {contenido}
    </Pressable>
  ) : (
    <View style={estilo}>{contenido}</View>
  );
}

const styles = StyleSheet.create({
  celda: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  texto: { flex: 1 },
  // M3: elemento de lista de dos líneas, sin separador
  dosLineas: { minHeight: 64, paddingVertical: Spacing.two, borderBottomWidth: 0 },
});

/** Grupo de celdas sobre superficie con esquinas de 10. */
export function GrupoAjustes({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return <View style={[grupo.grupo, { backgroundColor: theme.surface }]}>{children}</View>;
}

const grupo = StyleSheet.create({
  grupo: { borderRadius: Radius.surface, overflow: 'hidden' },
});
