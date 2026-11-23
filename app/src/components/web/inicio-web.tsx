import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Cadena } from '@/components/cadena';
import { CampoBusqueda } from '@/components/campo-busqueda';
import { FotoProducto } from '@/components/foto-producto';
import { Icono } from '@/components/icono';
import { ResumenLista } from '@/components/resumen-lista';
import { ThemedText } from '@/components/themed-text';
import { PaginaWeb } from '@/components/web/pagina-web';
import { Celda, FilaTabla, TituloColumna } from '@/components/web/tabla';
import { Cadenas, Spacing } from '@/constants/theme';
import { bajadasSemana, inicio } from '@/data/datos-ejemplo';
import { enumerar, formatoPrecio } from '@/utils/formato';

const abrirBusqueda = () => router.push('/screens/buscar');

/** W1 · Inicio a 1440: buscador grande, resumen de la lista y tabla de bajadas. */
export function InicioWeb() {
  return (
    <PaginaWeb>
      <View style={styles.cabecera}>
        <View style={styles.buscar}>
          <ThemedText type="display">{inicio.tituloWeb}</ThemedText>
          <ThemedText type="cuerpo" themeColor="textSecondary">
            {`Leídos a las ${inicio.hora} en ${Cadenas.length} cadenas: ${enumerar(Cadenas.map((c) => c.nombre))}.`}
          </ThemedText>
          <View style={styles.aire} />
          <CampoBusqueda onPress={abrirBusqueda} />
          <View style={styles.preguntar}>
            <Icono nombre="preguntar" size={20} themeColor="textSecondary" />
            <ThemedText type="cuerpo15" themeColor="textSecondary">
              ¿Tienes una duda?
            </ThemedText>
            <Pressable accessibilityRole="link" onPress={() => router.push('/preguntar')}>
              <ThemedText type="cuerpo15" themeColor="link" style={styles.subrayado}>
                Pregunta, por ejemplo, dónde sale más barata tu lista
              </ThemedText>
            </Pressable>
          </View>
        </View>
        <View style={styles.resumen}>
          <ResumenLista relleno={Spacing.four} />
        </View>
      </View>

      <View>
        <View style={styles.seccion}>
          <ThemedText type="titulo">Han bajado esta semana</ThemedText>
          <Pressable accessibilityRole="link" onPress={abrirBusqueda}>
            <ThemedText type="cuerpo15" themeColor="link" style={styles.subrayado}>
              Ver todas las bajadas
            </ThemedText>
          </Pressable>
        </View>

        <FilaTabla cabecera>
          <Celda cabecera>
            <TituloColumna>Producto</TituloColumna>
          </Celda>
          <Celda cabecera ancho={160}>
            <TituloColumna>Más barato en</TituloColumna>
          </Celda>
          <Celda cabecera ancho={140} derecha>
            <TituloColumna>Precio</TituloColumna>
          </Celda>
          <Celda cabecera ancho={140} derecha>
            <TituloColumna>Por unidad</TituloColumna>
          </Celda>
          <Celda cabecera ancho={200} derecha>
            <TituloColumna>Esta semana</TituloColumna>
          </Celda>
        </FilaTabla>
        {/* La API aún no calcula bajadas: esta tabla sale siempre de los datos de prueba. */}
        {bajadasSemana.map((p) => (
          <FilaTabla
            key={p.id}
            etiqueta={p.nombre}
            onPress={() => router.push({ pathname: '/producto/[id]', params: { id: p.id } })}>
            <Celda>
              <FotoProducto formato={p.formato} tamano={48} />
              <View style={styles.texto}>
                <ThemedText type="cuerpo15Medio">{p.nombre}</ThemedText>
                <ThemedText type="pie">{p.formato}</ThemedText>
              </View>
            </Celda>
            <Celda ancho={160}>
              <Cadena id={p.cadena} />
            </Celda>
            <Celda ancho={140} derecha>
              <ThemedText type="precio15">{formatoPrecio(p.precio)}</ThemedText>
            </Celda>
            <Celda ancho={140} derecha>
              <ThemedText type="pie">{p.precioUnidad}</ThemedText>
            </Celda>
            <Celda ancho={200} derecha>
              <ThemedText type="precio15" themeColor="down">
                {p.bajada ? `−${formatoPrecio(p.bajada)}` : '—'}
              </ThemedText>
            </Celda>
          </FilaTabla>
        ))}
      </View>
    </PaginaWeb>
  );
}

const styles = StyleSheet.create({
  cabecera: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.four },
  buscar: { width: 690, maxWidth: '58%', gap: Spacing.twelve, paddingTop: Spacing.four },
  aire: { height: Spacing.two },
  preguntar: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: Spacing.two,
    paddingVertical: Spacing.twelve,
  },
  resumen: { flex: 1 },
  seccion: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingBottom: Spacing.five,
  },
  texto: { flex: 1, gap: 2 },
  subrayado: { textDecorationLine: 'underline' },
});
