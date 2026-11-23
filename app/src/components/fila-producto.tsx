import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Cadena } from '@/components/cadena';
import { FotoProducto } from '@/components/foto-producto';
import { SelectorCantidad } from '@/components/selector-cantidad';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import type { ProductoCatalogo, ProductoLista } from '@/data/datos-ejemplo';
import { useTheme } from '@/hooks/use-theme';
import { formatoPrecio, nombreCadena, totalCadenas } from '@/utils/formato';

type BaseProps = {
  formato: string;
  nombre: string;
  info: ReactNode;
  derecha: ReactNode;
  onPress?: () => void;
};

function FilaBase({ formato, nombre, info, derecha, onPress }: BaseProps) {
  const theme = useTheme();
  const contenido = (
    <>
      <FotoProducto formato={formato} tamano={64} />
      <View style={styles.info}>
        <ThemedText type="cuerpo15Medio">{nombre}</ThemedText>
        {info}
      </View>
      {derecha}
    </>
  );

  const estilo = [styles.fila, { borderBottomColor: theme.hairline }];

  return onPress ? (
    <Pressable accessibilityRole="link" onPress={onPress} style={estilo}>
      {contenido}
    </Pressable>
  ) : (
    <View style={estilo}>{contenido}</View>
  );
}

/** Fila de catálogo: precio «desde» y cadena más barata. */
export function FilaCatalogo({ producto }: { producto: ProductoCatalogo }) {
  const theme = useTheme();
  const varias = producto.cadenasCon > 1;
  const nota = producto.bajada
    ? `Baja ${formatoPrecio(producto.bajada)} · en ${producto.cadenasCon} de ${totalCadenas} cadenas`
    : varias
      ? `En ${producto.cadenasCon} de ${totalCadenas} cadenas`
      : `Solo en ${nombreCadena(producto.cadena)}`;

  return (
    <FilaBase
      formato={producto.formato}
      nombre={producto.nombre}
      onPress={() => router.push({ pathname: '/producto/[id]', params: { id: producto.id } })}
      info={
        <>
          <ThemedText type="pie" style={producto.bajada ? { color: theme.down } : undefined}>
            {nota}
          </ThemedText>
          <Cadena id={producto.cadena} />
        </>
      }
      derecha={
        <View style={styles.precio}>
          {varias && <ThemedText type="pie">desde</ThemedText>}
          <ThemedText type="precio17">{formatoPrecio(producto.precio)}</ThemedText>
          <ThemedText type="pie">{producto.precioUnidad}</ThemedText>
        </View>
      }
    />
  );
}

/** Fila de lista: dónde es más barato y cantidad editable. */
export function FilaLista({
  producto,
  onCambiarCantidad,
}: {
  producto: ProductoLista;
  onCambiarCantidad: (cantidad: number) => void;
}) {
  return (
    <FilaBase
      formato={producto.formato}
      nombre={producto.nombre}
      info={
        <View style={styles.donde}>
          <ThemedText type="pie">{`${formatoPrecio(producto.precio)} en`}</ThemedText>
          <Cadena id={producto.cadena} />
        </View>
      }
      derecha={<SelectorCantidad cantidad={producto.cantidad} onCambiar={onCambiarCantidad} />}
    />
  );
}

const styles = StyleSheet.create({
  fila: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    paddingVertical: Spacing.twelve,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  info: { flex: 1, gap: Spacing.one },
  donde: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one },
  precio: { alignItems: 'flex-end' },
});
