import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { pistaError } from '@/api/http';
import { CampoBusqueda } from '@/components/campo-busqueda';
import { Chip } from '@/components/chip';
import { ControlSegmentado } from '@/components/control-segmentado';
import { EstadoVacio } from '@/components/estado-vacio';
import { FilaCargando } from '@/components/fila-cargando';
import { FilaCatalogo } from '@/components/fila-producto';
import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { VistaPreguntar } from '@/components/vista-preguntar';
import { BuscarWeb } from '@/components/web/buscar-web';
import { Cadenas, MaxContentWidth, Spacing } from '@/constants/theme';
import { MINIMO_LETRAS, textoRecuento, useBusqueda } from '@/data/busqueda';
import { busqueda } from '@/data/datos-ejemplo';
import { filtrosIniciales, setFiltros, useFiltros } from '@/data/estado-filtros';
import { useMargenPestanas } from '@/hooks/use-margen-pestanas';
import { useTheme } from '@/hooks/use-theme';
import { useAltoMenuWeb, useEscritorio } from '@/hooks/use-web';
import { plural } from '@/utils/formato';

const vistas = ['Buscar', 'Preguntar'] as const;
const filasCargando = [0, 1, 2, 3, 4, 5];
const abrirFiltros = () => router.push('/filtros');

/** B2 · Resultados de búsqueda, con B4 (sin resultados) y B5 (cargando). W2 en la web ancha. */
export default function Buscar() {
  const { q } = useLocalSearchParams<{ q?: string }>();
  const [consulta, setConsulta] = useState(q ?? busqueda.consulta);
  return useEscritorio() ? (
    <BuscarWeb consulta={consulta} onCambiar={setConsulta} />
  ) : (
    <BuscarMovil consulta={consulta} onCambiar={setConsulta} />
  );
}

type Props = { consulta: string; onCambiar: (texto: string) => void };

function BuscarMovil({ consulta, onCambiar }: Props) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const altoMenuWeb = useAltoMenuWeb();
  const margenPestanas = useMargenPestanas();
  const [vista, setVista] = useState<(typeof vistas)[number]>('Buscar');
  const { cadenas } = useFiltros();
  const filtradas = Cadenas.length - cadenas.length;

  return (
    <View style={[styles.raiz, { backgroundColor: theme.background }]}>
      <View style={[styles.cabecera, { paddingTop: insets.top + altoMenuWeb + Spacing.two }]}>
        <View style={styles.columna}>
          <ControlSegmentado opciones={vistas} seleccionada={vista} onCambiar={setVista} />
          {vista === 'Buscar' && (
            <>
              <CampoBusqueda valor={consulta} onChangeText={onCambiar} />
              <View style={styles.filtros}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Abrir filtros"
                  onPress={abrirFiltros}
                  style={styles.abrirFiltros}>
                  <Icono nombre="filtros" size={22} />
                </Pressable>
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={styles.chips}>
                  {filtradas > 0 && (
                    <Chip
                      activo
                      etiqueta={`Sin ${plural(filtradas, 'cadena')}`}
                      onPress={() => setFiltros((f) => ({ ...f, cadenas: filtrosIniciales.cadenas }))}
                    />
                  )}
                  <Chip etiqueta="Cadena" onPress={abrirFiltros} />
                  <Chip etiqueta="Orden" onPress={abrirFiltros} />
                </ScrollView>
              </View>
            </>
          )}
        </View>
      </View>

      {vista === 'Preguntar' ? (
        <VistaPreguntar margenInferior={margenPestanas} />
      ) : (
        <ScrollView
          style={styles.raiz}
          keyboardDismissMode="on-drag"
          contentContainerStyle={[
            styles.contenido,
            { paddingBottom: margenPestanas + Spacing.four },
          ]}>
          <View style={styles.columna}>
            <Resultados consulta={consulta} />
          </View>
        </ScrollView>
      )}
    </View>
  );
}

/** Lista de resultados con sus estados: escribe algo, cargando, error, vacío o filas. */
function Resultados({ consulta }: { consulta: string }) {
  const resultado = useBusqueda(consulta);
  const { cadenas } = useFiltros();
  const q = consulta.trim();

  if (q.length < MINIMO_LETRAS) {
    return (
      <EstadoVacio titulo="Busca un producto" texto="Escribe al menos dos letras del nombre o la marca." />
    );
  }
  if (resultado.estado === 'cargando') {
    return (
      <>
        <ThemedText type="pie" style={styles.recuento}>
          {busqueda.cargando.texto}
        </ThemedText>
        {filasCargando.map((i) => (
          <FilaCargando key={i} />
        ))}
      </>
    );
  }
  if (resultado.estado === 'error') {
    return (
      <EstadoVacio
        titulo="No hemos podido cargar los precios"
        texto={`${resultado.mensaje}. ${pistaError}`}
        accion={{ etiqueta: 'Reintentar', onPress: resultado.reintentar }}
      />
    );
  }

  const { productos, total, parecidos } = resultado.datos;
  if (productos.length === 0) {
    const conFiltro = cadenas.length < Cadenas.length;
    return (
      <EstadoVacio
        titulo={`Nada con «${q}»`}
        texto={
          conFiltro
            ? 'Puede que esté en las cadenas que has quitado en los filtros.'
            : 'Prueba con otra palabra o marca.'
        }
        accion={
          conFiltro
            ? { etiqueta: 'Quitar filtros', onPress: () => setFiltros(filtrosIniciales) }
            : undefined
        }
      />
    );
  }

  return (
    <>
      <ThemedText type="pie" style={styles.recuento}>
        {textoRecuento(productos.length, total, parecidos)}
      </ThemedText>
      {productos.map((p) => (
        <FilaCatalogo key={p.id} producto={p} />
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  raiz: { flex: 1 },
  cabecera: { paddingHorizontal: Spacing.three, alignItems: 'center' },
  columna: { width: '100%', maxWidth: MaxContentWidth, gap: Spacing.two },
  filtros: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  abrirFiltros: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  chips: { gap: Spacing.two, alignItems: 'center' },
  contenido: { paddingHorizontal: Spacing.three, alignItems: 'center' },
  recuento: { paddingTop: Spacing.two, paddingBottom: Spacing.one },
});
