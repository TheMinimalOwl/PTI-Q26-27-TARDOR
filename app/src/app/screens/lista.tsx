import { router } from 'expo-router';
import { Pressable, Share, StyleSheet, View } from 'react-native';

import { Boton } from '@/components/boton';
import { ContenedorPestana } from '@/components/contenedor-pestana';
import { EstadoVacio } from '@/components/estado-vacio';
import { FilaLista } from '@/components/fila-producto';
import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useCesta } from '@/data/cesta';
import { listaVacia, nombreLista } from '@/data/datos-ejemplo';
import { cambiarCantidad } from '@/data/estado-lista';
import { formatoPrecio, nombreCadena, plural } from '@/utils/formato';

/** E1 · Lista (con E3 lista vacía) */
export default function Lista() {
  const cesta = useCesta();
  const productos = cesta.lista;
  const vacia = productos.length === 0;
  // Repartida: cada producto donde es más barato. Mientras se calcula, con los precios guardados.
  const repartida = cesta.estado === 'ok' ? cesta.datos.repartida : null;
  const total = repartida?.total ?? productos.reduce((s, p) => s + p.precio * p.cantidad, 0);

  const compartir = () =>
    Share.share({
      message: [
        nombreLista,
        ...productos.map(
          (p) =>
            `${p.cantidad} × ${p.nombre}: ${formatoPrecio(p.precio)} en ${nombreCadena(p.cadena)}`,
        ),
        `Total: ${formatoPrecio(total)}`,
      ].join('\n'),
    });

  return (
    <ContenedorPestana
      titulo="Lista"
      subtitulo={vacia ? undefined : `${nombreLista} · ${plural(productos.length, 'producto')}`}
      accion={{ icono: 'compartir', etiqueta: 'Compartir lista', onPress: compartir }}
      pie={
        vacia ? undefined : (
          <View style={styles.total}>
            <View style={styles.importe}>
              <ThemedText type="precio22" themeColor="title">
                {formatoPrecio(total)}
              </ThemedText>
              {repartida && repartida.tiendas.length > 0 && (
                <Pressable
                  accessibilityRole="link"
                  hitSlop={8}
                  onPress={() => router.push('/ruta')}>
                  <ThemedText type="pie" themeColor="link" style={styles.subrayado}>
                    {repartida.tiendas.length === 1
                      ? 'Ver cómo llegar a la tienda'
                      : `Ver ruta por las ${repartida.tiendas.length} tiendas`}
                  </ThemedText>
                </Pressable>
              )}
            </View>
            <Boton etiqueta="Comparar cesta" onPress={() => router.push('/comparar')} />
          </View>
        )
      }>
      <View style={styles.aire} />

      {vacia ? (
        // El escáner necesita expo-camera; mientras, el botón abre Buscar.
        <EstadoVacio
          titulo={listaVacia.titulo}
          texto={listaVacia.texto}
          accion={{
            etiqueta: 'Escanear código de barras',
            onPress: () => router.push('/screens/buscar'),
          }}
        />
      ) : (
        <>
          {productos.map((producto) => (
            <FilaLista
              key={producto.id}
              producto={producto}
              onCambiarCantidad={(cantidad) => cambiarCantidad(producto.id, cantidad)}
            />
          ))}
          <Pressable
            accessibilityRole="link"
            onPress={() => router.push('/screens/buscar')}
            style={styles.anadir}>
            <Icono nombre="mas" size={20} themeColor="link" />
            <ThemedText type="cuerpo15Medio" themeColor="link">
              Añadir producto
            </ThemedText>
          </Pressable>
        </>
      )}
    </ContenedorPestana>
  );
}

const styles = StyleSheet.create({
  aire: { height: Spacing.two },
  anadir: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  total: { flexDirection: 'row', alignItems: 'center', gap: Spacing.twelve },
  importe: { flex: 1 },
  subrayado: { textDecorationLine: 'underline' },
});
