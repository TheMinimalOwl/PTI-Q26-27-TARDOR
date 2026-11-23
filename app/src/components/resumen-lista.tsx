import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { pistaError } from '@/api/http';
import { Boton } from '@/components/boton';
import { Cadena } from '@/components/cadena';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useCesta } from '@/data/cesta';
import { nombreLista } from '@/data/datos-ejemplo';
import { useTheme } from '@/hooks/use-theme';
import { formatoPrecio, plural } from '@/utils/formato';

/** Tarjeta de Inicio (B1/W1): dónde sale más barata la lista completa y cuánto repartida. */
export function ResumenLista({ relleno = Spacing.three }: { relleno?: number }) {
  const theme = useTheme();
  const cesta = useCesta();
  const productos = cesta.lista.length;

  return (
    <View style={[styles.resumen, { backgroundColor: theme.surface, padding: relleno }]}>
      <ThemedText type="pieMedio" themeColor="textSecondary">
        {`${nombreLista} · ${plural(productos, 'producto')}`}
      </ThemedText>
      <Contenido cesta={cesta} productos={productos} />
    </View>
  );
}

function Contenido({ cesta, productos }: { cesta: ReturnType<typeof useCesta>; productos: number }) {
  if (productos === 0) {
    return (
      <>
        <ThemedText type="cuerpo15">Añade productos para ver dónde te sale más barata.</ThemedText>
        <Boton etiqueta="Buscar productos" onPress={() => router.push('/screens/buscar')} />
      </>
    );
  }
  if (cesta.estado === 'cargando') {
    return <ThemedText type="cuerpo15">Comparando la lista en las cadenas…</ThemedText>;
  }
  if (cesta.estado === 'error') {
    return (
      <>
        <ThemedText type="cuerpo15">{`${cesta.mensaje}. ${pistaError}`}</ThemedText>
        <Boton tipo="secundario" etiqueta="Reintentar" onPress={cesta.reintentar} />
      </>
    );
  }

  const { completas, repartida } = cesta.datos;
  const mejor = completas[0];
  const reparto = `Repartida en ${plural(repartida.tiendas.length, 'tienda')}: ${formatoPrecio(repartida.total)}`;
  const ahorro = repartida.ahorro && repartida.ahorro > 0 ? `, ${formatoPrecio(repartida.ahorro)} menos` : '';

  return (
    <>
      <View style={styles.mejor}>
        {mejor ? (
          <>
            <View style={styles.donde}>
              <ThemedText type="cuerpo15">Completa, más barata en</ThemedText>
              <Cadena id={mejor.cadena} />
            </View>
            <ThemedText type="precio34">{formatoPrecio(mejor.total)}</ThemedText>
          </>
        ) : (
          <ThemedText type="cuerpo15">Ninguna cadena tiene toda tu lista.</ThemedText>
        )}
        <ThemedText type="pie">{reparto + ahorro}</ThemedText>
      </View>
      <Boton etiqueta="Comparar lista" onPress={() => router.push('/comparar')} />
    </>
  );
}

const styles = StyleSheet.create({
  resumen: { gap: Spacing.twelve, borderRadius: Radius.surface },
  mejor: { gap: Spacing.one },
  donde: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one, flexWrap: 'wrap' },
});
