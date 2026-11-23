import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { serieDesdeHistorial } from '@/api/producto';
import { Boton } from '@/components/boton';
import { Cadena } from '@/components/cadena';
import { FotoProducto } from '@/components/foto-producto';
import { GraficaPrecio } from '@/components/grafica-precio';
import { MejorPrecio, type PropsFicha } from '@/components/mejor-precio';
import { ThemedText } from '@/components/themed-text';
import { PaginaWeb } from '@/components/web/pagina-web';
import { Celda, FilaTabla, PrecioCelda, TituloColumna } from '@/components/web/tabla';
import { Spacing } from '@/constants/theme';
import { anadirALista } from '@/data/estado-lista';
import { filasPorPrecio } from '@/data/ficha';
import { useTheme } from '@/hooks/use-theme';
import { formatoPrecio } from '@/utils/formato';

/** W3 · Detalle de producto a 1440: tabla por cadena y evolución de 2 años. */
export function ProductoWeb(props: PropsFicha) {
  const { ficha, caida } = props;
  const theme = useTheme();
  const serie = serieDesdeHistorial(ficha.puntos);
  // De más barato a más caro; las ofertas son un chip y no cambian el orden.
  const filas = filasPorPrecio(ficha.filas);

  return (
    <PaginaWeb>
      <View style={styles.migas}>
        <Miga texto="Inicio" onPress={() => router.push('/screens/inicio')} />
        {ficha.categoria && (
          <>
            <ThemedText type="pie">/</ThemedText>
            <Miga
              texto={ficha.categoria}
              onPress={() =>
                router.push({ pathname: '/screens/buscar', params: { q: ficha.categoria! } })
              }
            />
          </>
        )}
        <ThemedText type="pie">/</ThemedText>
        <ThemedText type="pie" themeColor="text" numberOfLines={1}>
          {ficha.nombreCompleto}
        </ThemedText>
      </View>

      <View style={styles.cabecera}>
        <FotoProducto formato={ficha.formato} tamano={384} />
        <View style={styles.datos}>
          <View>
            <ThemedText type="display">{ficha.nombre}</ThemedText>
            <ThemedText type="cuerpo" themeColor="textSecondary">
              {ficha.detalle}
            </ThemedText>
          </View>
          <MejorPrecio {...props} />
          <View style={styles.acciones}>
            <Boton
              etiqueta="Añadir a la lista"
              onPress={() => {
                anadirALista(ficha.paraLista);
                router.push('/screens/lista');
              }}
            />
            <Boton
              tipo="secundario"
              etiqueta="Avisarme si baja"
              onPress={() => router.push('/avisos')}
            />
          </View>
        </View>
      </View>

      <View>
        <ThemedText type="titulo" style={styles.titulo}>
          Precio por cadena
        </ThemedText>
        <FilaTabla cabecera>
          <Celda cabecera ancho={260}>
            <TituloColumna>Cadena</TituloColumna>
          </Celda>
          <Celda cabecera ancho={80} derecha>
            <TituloColumna>Precio</TituloColumna>
          </Celda>
          <Celda cabecera ancho={160} derecha>
            <TituloColumna>Por unidad</TituloColumna>
          </Celda>
          <Celda cabecera ancho={420}>
            <TituloColumna>Oferta</TituloColumna>
          </Celda>
          <Celda cabecera>
            <TituloColumna>{ficha.columnaDetalle}</TituloColumna>
          </Celda>
        </FilaTabla>
        {filas.map((fila) => {
          const sinRespuesta = fila.cadena === caida;
          const disponible = fila.precio !== undefined && !sinRespuesta;
          const mejor = fila.cadena === ficha.mejor?.cadena && !caida;
          const abrir = fila.idProducto
            ? () => router.push({ pathname: '/producto/[id]', params: { id: fila.idProducto! } })
            : undefined;
          return (
            <FilaTabla
              key={fila.cadena}
              mejor={mejor}
              onPress={abrir}
              etiqueta={fila.detalle}>
              <Celda ancho={260}>
                <Cadena id={fila.cadena} secundario={!disponible} />
              </Celda>
              <Celda ancho={80} derecha>
                <PrecioCelda
                  texto={disponible ? formatoPrecio(fila.precio!) : undefined}
                  mejor={mejor}
                />
              </Celda>
              <Celda ancho={160} derecha>
                <ThemedText type="cuerpo15" themeColor={mejor ? 'onTint' : 'textSecondary'}>
                  {disponible ? (fila.precioUnidad ?? '—') : '—'}
                </ThemedText>
              </Celda>
              <Celda ancho={420}>
                {mejor ? (
                  <ThemedText type="pie" themeColor="onTint">
                    Más barato
                  </ThemedText>
                ) : disponible && fila.oferta ? (
                  <View style={[styles.oferta, { backgroundColor: theme.tint }]}>
                    <ThemedText type="pieMedio" themeColor="onTint">
                      {fila.oferta}
                    </ThemedText>
                  </View>
                ) : (
                  <ThemedText type="pie">—</ThemedText>
                )}
              </Celda>
              <Celda>
                <ThemedText type="pie" themeColor={mejor ? 'onTint' : 'textSecondary'}>
                  {sinRespuesta
                    ? 'Precio no disponible ahora'
                    : disponible
                      ? fila.detalle
                      : 'Sin este producto'}
                </ThemedText>
              </Celda>
            </FilaTabla>
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
          <View style={styles.seccion}>
            <ThemedText type="titulo">Evolución del precio</ThemedText>
            <Miga
              texto="Ver histórico"
              onPress={() =>
                router.push({ pathname: '/producto/[id]/evolucion', params: { id: ficha.id } })
              }
            />
          </View>
          <ThemedText type="pie">{ficha.subtituloEvolucion}</ThemedText>
          <GraficaPrecio
            valores={serie.valores}
            guias={serie.guias}
            eje={serie.eje}
            maximo={serie.maximo}
            alto={260}
          />
        </View>
      )}
    </PaginaWeb>
  );
}

function Miga({ texto, onPress }: { texto: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="link" onPress={onPress}>
      <ThemedText type="pie" themeColor="link" style={styles.subrayado}>
        {texto}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  migas: { flexDirection: 'row', alignItems: 'center', gap: Spacing.twelve, marginTop: -Spacing.two },
  cabecera: { flexDirection: 'row', gap: Spacing.four, alignItems: 'flex-start' },
  datos: { flex: 1, gap: Spacing.four, paddingTop: Spacing.two },
  acciones: { flexDirection: 'row', gap: Spacing.twelve },
  titulo: { paddingBottom: Spacing.four },
  seccion: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingBottom: Spacing.one,
  },
  oferta: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  nota: { paddingTop: Spacing.two },
  subrayado: { textDecorationLine: 'underline' },
});
