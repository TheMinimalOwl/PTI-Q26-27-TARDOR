import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Boton } from '@/components/boton';
import { ControlSegmentado } from '@/components/control-segmentado';
import { FilaPrecio } from '@/components/fila-precio';
import { Icono } from '@/components/icono';
import { EstadoVacio } from '@/components/estado-vacio';
import { MapaRuta } from '@/components/mapa-ruta';
import { ThemedText } from '@/components/themed-text';
import { Fonts, SinContornoWeb, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { useCesta } from '@/data/cesta';
import { ruta } from '@/data/datos-ejemplo';
import { paradasDe, type Parada } from '@/data/ruta';
import { useTheme } from '@/hooks/use-theme';
import { useAltoMenuWeb } from '@/hooks/use-web';
import { formatoPrecio, nombreCadena, plural } from '@/utils/formato';

const ALTO_MAPA = 340;

/** Abre la app de mapas del sistema (o Google Maps en la web) con las paradas en orden. */
function empezarRuta(paradas: Parada[], modo: (typeof ruta.modos)[number]) {
  const ubicadas = paradas.flatMap((p) => (p.coordenadas ? [p.coordenadas] : []));
  if (ubicadas.length === 0) return;
  const coord = (c: NonNullable<Parada['coordenadas']>) => `${c.latitude},${c.longitude}`;
  const destino = ubicadas[ubicadas.length - 1];
  const intermedias = ubicadas.slice(0, -1).map(coord).join('|');
  const viaje = modo === 'A pie' ? 'walking' : 'driving';
  Linking.openURL(
    `https://www.google.com/maps/dir/?api=1&destination=${coord(destino)}&waypoints=${encodeURIComponent(intermedias)}&travelmode=${viaje}`,
  );
}

function SinPermiso({ onContinuar }: { onContinuar: () => void }) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const altoMenuWeb = useAltoMenuWeb();
  const [origen, setOrigen] = useState('');

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={[styles.sinPermiso, { paddingTop: insets.top + altoMenuWeb + 44 }]}>
      <View style={styles.columna}>
        <ThemedText type="display">Ruta</ThemedText>
        <View style={[styles.permiso, { backgroundColor: theme.backgroundElement }]}>
          <ThemedText type="titulo" themeColor="text">
            {ruta.sinPermiso.titulo}
          </ThemedText>
          <ThemedText type="cuerpo15" themeColor="textSecondary">
            {ruta.sinPermiso.texto}
          </ThemedText>
          <Boton
            etiqueta="Permitir ubicación"
            onPress={() => Linking.openSettings()}
            style={styles.permitir}
          />
        </View>
        <View style={styles.origen}>
          <ThemedText type="pieMedio">{ruta.sinPermiso.alternativa}</ThemedText>
          <View style={[styles.campo, { backgroundColor: theme.backgroundElement }]}>
            <Icono nombre="buscar" size={20} themeColor="textSecondary" />
            <TextInput
              value={origen}
              onChangeText={setOrigen}
              onSubmitEditing={() => origen.trim() && onContinuar()}
              placeholder={ruta.sinPermiso.placeholder}
              placeholderTextColor={theme.textSecondary}
              returnKeyType="go"
              accessibilityLabel={ruta.sinPermiso.placeholder}
              style={[styles.entrada, { color: theme.text }]}
            />
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

/**
 * F1 · Ruta de la compra repartida, o hasta una sola tienda con `?cadena=bonarea`.
 * F2 sin permiso de ubicación: `?sinPermiso=1`.
 */
export default function Ruta() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const altoMenuWeb = useAltoMenuWeb();
  const params = useLocalSearchParams<{ sinPermiso?: string; cadena?: string }>();
  const [sinPermiso, setSinPermiso] = useState(params.sinPermiso === '1');
  const [modo, setModo] = useState<(typeof ruta.modos)[number]>('A pie');
  const cesta = useCesta();

  const volver = (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Volver"
      onPress={() => router.back()}
      style={[
        styles.volver,
        { top: insets.top + altoMenuWeb + Spacing.two, backgroundColor: theme.surface },
      ]}>
      <Icono nombre="atras" size={20} themeColor="link" />
    </Pressable>
  );

  if (sinPermiso) {
    return (
      <View style={styles.raiz}>
        <SinPermiso onContinuar={() => setSinPermiso(false)} />
        {volver}
      </View>
    );
  }

  if (cesta.estado !== 'ok' || cesta.lista.length === 0) {
    return (
      <View
        style={[
          styles.raiz,
          styles.sinPermiso,
          { backgroundColor: theme.background, paddingTop: insets.top + altoMenuWeb + 72 },
        ]}>
        <View style={styles.columna}>
          {cesta.estado === 'cargando' ? (
            <ThemedText type="pie">Calculando la ruta…</ThemedText>
          ) : (
            <EstadoVacio
              titulo="No hay ruta que trazar"
              texto={
                cesta.estado === 'error'
                  ? cesta.mensaje
                  : 'Añade productos a la lista para ver dónde comprarlos.'
              }
              accion={
                cesta.estado === 'error'
                  ? { etiqueta: 'Reintentar', onPress: cesta.reintentar }
                  : undefined
              }
            />
          )}
        </View>
        {volver}
      </View>
    );
  }

  const { repartida, completas, incompletas } = cesta.datos;
  const mejor = completas[0];
  // Con `cadena`, toda la lista en esa tienda; si no, cada producto donde es más barato.
  const unaTienda = params.cadena
    ? [...completas, ...incompletas].find((c) => c.cadena === params.cadena)
    : undefined;
  const paradas = paradasDe(
    unaTienda ? { ...cesta.datos, repartida: { ...repartida, tiendas: [unaTienda] } } : cesta.datos,
    cesta.lista,
  );
  const total = unaTienda?.total ?? repartida.total;
  const resumen = [plural(paradas.length, 'parada'), formatoPrecio(total)].join(' · ');

  return (
    <View style={[styles.raiz, { backgroundColor: theme.background }]}>
      <MapaRuta paradas={paradas} alto={ALTO_MAPA + insets.top + altoMenuWeb} />

      <View style={[styles.hoja, { backgroundColor: theme.surface }]}>
        <View style={[styles.asa, { backgroundColor: theme.backgroundSelected }]} />
        <ScrollView
          contentContainerStyle={[
            styles.contenido,
            { paddingBottom: insets.bottom + Spacing.three },
          ]}>
          <View style={styles.columna}>
            <View style={styles.titulo}>
              <ThemedText type="titulo">
                {unaTienda ? `Cómo llegar a ${nombreCadena(unaTienda.cadena)}` : 'Ruta de tu lista'}
              </ThemedText>
              <ThemedText type="cuerpo15Medio" themeColor="textSecondary">
                {resumen}
              </ThemedText>
            </View>

            <ControlSegmentado opciones={ruta.modos} seleccionada={modo} onCambiar={setModo} />

            <View>
              {paradas.map((p, i) => (
                <FilaPrecio
                  key={p.cadena}
                  cadena={p.cadena}
                  detalle={`${i + 1} · ${p.direccion} · ${p.productos}`}
                  valor={formatoPrecio(p.total)}
                  nota={p.unidades === 1 ? '1 producto' : `${p.unidades} productos`}
                />
              ))}
            </View>

            <View>
              <ThemedText type="precio22" themeColor="title">
                {formatoPrecio(total)}
              </ThemedText>
              {!unaTienda && mejor && repartida.ahorro !== null && repartida.ahorro > 0 && (
                <ThemedText type="pie">
                  {`${formatoPrecio(repartida.ahorro)} menos que todo en ${nombreCadena(mejor.cadena)}`}
                </ThemedText>
              )}
            </View>

            <View>
              <Boton etiqueta="Empezar ruta" onPress={() => empezarRuta(paradas, modo)} />
              {!unaTienda && mejor && (
                <Boton
                  tipo="texto"
                  etiqueta={`Prefiero una sola tienda: ${nombreCadena(mejor.cadena)}, ${formatoPrecio(mejor.total)}`}
                  onPress={() => router.setParams({ cadena: mejor.cadena })}
                  style={styles.unaTienda}
                />
              )}
            </View>
          </View>
        </ScrollView>
      </View>

      {volver}
    </View>
  );
}

const styles = StyleSheet.create({
  raiz: { flex: 1 },
  volver: {
    position: 'absolute',
    left: Spacing.three,
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 1px 4px rgba(0, 0, 0, 0.12)',
  },
  hoja: {
    flex: 1,
    marginTop: -Radius.surface,
    borderTopLeftRadius: Radius.surface,
    borderTopRightRadius: Radius.surface,
    overflow: 'hidden',
  },
  asa: {
    alignSelf: 'center',
    width: 36,
    height: 5,
    borderRadius: Radius.pill,
    marginTop: Spacing.two,
  },
  contenido: { paddingHorizontal: Spacing.three, alignItems: 'center' },
  columna: { width: '100%', maxWidth: MaxContentWidth, gap: Spacing.twelve },
  titulo: { gap: 2, paddingTop: Spacing.two },
  unaTienda: { marginTop: Spacing.two },
  sinPermiso: { paddingHorizontal: Spacing.three, alignItems: 'center' },
  permiso: {
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Radius.surface,
    marginTop: Spacing.two,
  },
  permitir: { marginTop: Spacing.two },
  origen: { gap: Spacing.two, marginTop: Spacing.four },
  campo: {
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingHorizontal: Spacing.twelve,
    borderRadius: Radius.surface,
  },
  entrada: { flex: 1, fontFamily: Fonts.sans, fontSize: 17, padding: 0, ...SinContornoWeb },
});
