import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { pistaError } from '@/api/http';
import { serieDesdeHistorial } from '@/api/producto';
import { Boton } from '@/components/boton';
import { BotonCompartir } from '@/components/boton-compartir';
import { CabeceraSeccion } from '@/components/cabecera-seccion';
import { EstadoVacio } from '@/components/estado-vacio';
import { FilaPrecio } from '@/components/fila-precio';
import { FotoProducto } from '@/components/foto-producto';
import { GraficaPrecio } from '@/components/grafica-precio';
import { MejorPrecio, type PropsFicha } from '@/components/mejor-precio';
import { PantallaDetalle } from '@/components/pantalla-detalle';
import { ThemedText } from '@/components/themed-text';
import { ProductoWeb } from '@/components/web/producto-web';
import { Spacing } from '@/constants/theme';
import { errorPrecios } from '@/data/datos-ejemplo';
import { anadirALista } from '@/data/estado-lista';
import { useFicha } from '@/data/ficha';
import { useEscritorio } from '@/hooks/use-web';
import { formatoPrecio } from '@/utils/formato';

/**
 * C1 · Detalle de producto (W3 en la web ancha), con C3 si una cadena no responde:
 * `/producto/aceite?error=condis`.
 */
export default function DetalleProducto() {
  const { id, error } = useLocalSearchParams<{ id: string; error?: string }>();
  const ficha = useFicha(id);
  // C3: ejemplo de cadena caída (solo datos de prueba); «Reintentar» la recupera.
  const [caida, setCaida] = useState(error === errorPrecios.cadena ? error : null);
  const escritorio = useEscritorio();

  if (ficha.estado !== 'ok' || ficha.datos === null) {
    return (
      <PantallaDetalle>
        <Stack.Screen options={{ title: '' }} />
        {ficha.estado === 'cargando' ? (
          <ThemedText type="pie">Cargando precios…</ThemedText>
        ) : ficha.estado === 'error' ? (
          <EstadoVacio
            titulo="No hemos podido cargar este producto"
            texto={`${ficha.mensaje}. ${pistaError}`}
            accion={{ etiqueta: 'Reintentar', onPress: ficha.reintentar }}
          />
        ) : (
          <EstadoVacio
            titulo="Aún no tenemos este producto"
            texto="Lo estamos añadiendo. Mientras, puedes buscar otro parecido."
            accion={{ etiqueta: 'Buscar', onPress: () => router.replace('/screens/buscar') }}
          />
        )}
      </PantallaDetalle>
    );
  }

  const props = { ficha: ficha.datos, caida, onReintentar: () => setCaida(null) };
  return escritorio ? <ProductoWeb {...props} /> : <ProductoMovil {...props} />;
}

function ProductoMovil(props: PropsFicha) {
  const { ficha, caida } = props;
  const serie = serieDesdeHistorial(ficha.puntos);

  return (
    <PantallaDetalle
      pie={
        <View style={styles.acciones}>
          <Boton
            tipo="secundario"
            etiqueta="Avisarme si baja"
            onPress={() => router.push('/avisos')}
          />
          <Boton
            etiqueta="Añadir a la lista"
            onPress={() => {
              anadirALista(ficha.paraLista);
              router.navigate('/screens/lista');
            }}
            style={styles.espacio}
          />
        </View>
      }>
      <Stack.Screen
        options={{ title: '', headerRight: () => <BotonCompartir mensaje={ficha.compartir} /> }}
      />

      <View style={styles.producto}>
        <FotoProducto formato={ficha.formato} tamano={96} />
        <View style={styles.espacio}>
          <ThemedText type="titulo">{ficha.nombre}</ThemedText>
          <ThemedText type="pie">{ficha.detalle}</ThemedText>
        </View>
      </View>

      <MejorPrecio {...props} />

      <View>
        <CabeceraSeccion titulo="Precio por cadena" />
        {ficha.filas.map((fila) => {
          const mejor = fila.cadena === ficha.mejor?.cadena && !caida;
          const sinRespuesta = fila.cadena === caida;
          const disponible = fila.precio !== undefined && !sinRespuesta;
          return (
            <FilaPrecio
              key={fila.cadena}
              cadena={fila.cadena}
              mejor={mejor}
              detalle={
                sinRespuesta
                  ? 'Precio no disponible ahora'
                  : disponible
                    ? fila.detalle
                    : 'Sin este producto'
              }
              valor={disponible ? formatoPrecio(fila.precio!) : undefined}
              nota={disponible ? (mejor ? 'Más barato' : fila.precioUnidad) : undefined}
              oferta={disponible ? fila.oferta : undefined}
            />
          );
        })}
        {ficha.nota && (
          <ThemedText type="pie" style={styles.nota}>
            {ficha.nota}
          </ThemedText>
        )}
      </View>

      {serie && (
        <View>
          <CabeceraSeccion
            titulo="Evolución del precio"
            enlace="Ver histórico"
            onPressEnlace={() =>
              router.push({ pathname: '/producto/[id]/evolucion', params: { id: ficha.id } })
            }
          />
          <GraficaPrecio
            valores={serie.valores}
            guias={serie.guias}
            eje={serie.eje}
            maximo={serie.maximo}
            alto={150}
          />
        </View>
      )}
    </PantallaDetalle>
  );
}

const styles = StyleSheet.create({
  espacio: { flex: 1 },
  producto: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three },
  acciones: { flexDirection: 'row', gap: Spacing.twelve },
  nota: { paddingTop: Spacing.two },
});
