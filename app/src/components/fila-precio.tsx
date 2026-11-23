import { StyleSheet, View } from 'react-native';

import { Cadena } from '@/components/cadena';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing, type SlugCadena } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = {
  cadena: SlugCadena;
  /** Tienda, distancia o «x de 5 productos». */
  detalle?: string;
  /** Precio principal; sin él se muestra «—». */
  valor?: string;
  /** Debajo del precio: €/unidad, diferencia o «Más barato». */
  nota?: string;
  oferta?: string;
  /** Mejor opción: fondo de tinte paja. */
  mejor?: boolean;
  /** Cesta incompleta o cadena sin el producto: todo en tono secundario. */
  apagada?: boolean;
};

/** Precio en una cadena. El mejor va sobre tinte; la oferta es un chip y no cambia el orden. */
export function FilaPrecio({ cadena, detalle, valor, nota, oferta, mejor, apagada }: Props) {
  const theme = useTheme();
  const tono = mejor ? 'onTint' : 'textSecondary';

  return (
    <View
      style={[
        styles.fila,
        mejor
          ? { backgroundColor: theme.tint, borderRadius: Radius.surface }
          : { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.hairline },
      ]}>
      <View style={styles.info}>
        <Cadena id={cadena} secundario={apagada} />
        {detalle && (
          <ThemedText type="pie" themeColor={tono}>
            {detalle}
          </ThemedText>
        )}
        {oferta && (
          <View style={[styles.oferta, { backgroundColor: theme.tint }]}>
            <ThemedText type="pieMedio" themeColor="onTint">
              {oferta}
            </ThemedText>
          </View>
        )}
      </View>
      <View style={styles.precio}>
        <ThemedText
          type={apagada ? 'precio15' : 'precio17'}
          themeColor={valor && !apagada ? 'text' : 'textSecondary'}>
          {valor ?? '—'}
        </ThemedText>
        {nota && (
          <ThemedText type="pie" themeColor={tono}>
            {nota}
          </ThemedText>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fila: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    paddingHorizontal: Spacing.three,
    paddingVertical: 10,
  },
  info: { flex: 1, gap: Spacing.one, alignItems: 'flex-start' },
  oferta: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  precio: { alignItems: 'flex-end' },
});
