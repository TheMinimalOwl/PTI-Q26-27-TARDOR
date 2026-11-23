import { StyleSheet, View } from 'react-native';

import { Aviso } from '@/components/aviso';
import { Cadena } from '@/components/cadena';
import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { errorPrecios } from '@/data/datos-ejemplo';
import type { FichaProducto } from '@/data/ficha';
import { formatoPrecio, nombreCadena } from '@/utils/formato';

export type PropsFicha = {
  ficha: FichaProducto;
  /** Cadena cuya web no responde (C3). */
  caida: string | null;
  onReintentar: () => void;
};

/** Precio más barato, tendencia o el aviso de C3. */
export function MejorPrecio({ ficha, caida, onReintentar }: PropsFicha) {
  if (caida) {
    return (
      <Aviso
        icono="alerta"
        titulo={`Falta el precio de ${nombreCadena(caida)}`}
        texto={errorPrecios.texto}
        accion={{ etiqueta: 'Reintentar', onPress: onReintentar }}
      />
    );
  }
  if (!ficha.mejor) {
    return (
      <ThemedText type="cuerpo15" themeColor="textSecondary">
        Sin precio actual.
      </ThemedText>
    );
  }
  return (
    <View style={styles.mejor}>
      <View style={styles.precio}>
        <ThemedText type="precio34" themeColor="text">
          {formatoPrecio(ficha.mejor.precio)}
        </ThemedText>
        <ThemedText type="cuerpo15" themeColor="textSecondary">
          en
        </ThemedText>
        <Cadena id={ficha.mejor.cadena} />
      </View>
      {ficha.tendencia && (
        <View style={styles.tendencia}>
          <Icono nombre="bajada" size={16} themeColor="down" />
          <ThemedText type="pieMedio" themeColor="down">
            {ficha.tendencia}
          </ThemedText>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  mejor: { gap: Spacing.one },
  precio: { flexDirection: 'row', alignItems: 'baseline', gap: Spacing.two },
  tendencia: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one },
});
