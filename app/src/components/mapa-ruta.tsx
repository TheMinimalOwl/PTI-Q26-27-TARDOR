import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';

import { Cadena } from '@/components/cadena';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import type { Parada } from '@/data/ruta';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useTheme } from '@/hooks/use-theme';

type Props = { paradas: Parada[]; alto: number };

/** Plano con las paradas numeradas y la línea del recorrido. */
export function MapaRuta({ paradas, alto }: Props) {
  const theme = useTheme();
  const oscuro = useColorScheme() === 'dark';
  // En Android un marcador con vista propia sale en negro si deja de seguir cambios antes de
  // pintarse; se sigue un momento y luego se congela para no redibujar en cada frame.
  const [pintados, setPintados] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setPintados(true), 1000);
    return () => clearTimeout(t);
  }, []);
  const ubicadas = paradas.flatMap((p) => (p.coordenadas ? [{ ...p, coordenadas: p.coordenadas }] : []));
  const puntos = ubicadas.map((p) => p.coordenadas);
  if (puntos.length === 0) return <View style={{ height: alto, backgroundColor: theme.backgroundElement }} />;
  const lats = puntos.map((p) => p.latitude);
  const lngs = puntos.map((p) => p.longitude);

  return (
    <MapView
      style={{ height: alto }}
      userInterfaceStyle={oscuro ? 'dark' : 'light'}
      showsUserLocation
      showsPointsOfInterests={false}
      toolbarEnabled={false}
      initialRegion={{
        latitude: (Math.min(...lats) + Math.max(...lats)) / 2,
        longitude: (Math.min(...lngs) + Math.max(...lngs)) / 2,
        // Con una sola parada, un encuadre de barrio.
        latitudeDelta: Math.max((Math.max(...lats) - Math.min(...lats)) * 2.2, 0.01),
        longitudeDelta: Math.max((Math.max(...lngs) - Math.min(...lngs)) * 1.6, 0.01),
      }}>
      <Polyline coordinates={puntos} strokeColor={theme.primary} strokeWidth={3} />
      {ubicadas.map((p, i) => (
        <Marker
          key={p.cadena}
          coordinate={p.coordenadas}
          anchor={{ x: 0.1, y: 0.5 }}
          tracksViewChanges={!pintados}>
          <View style={[styles.parada, { backgroundColor: theme.surface }]}>
            <View style={[styles.numero, { backgroundColor: theme.primary }]}>
              <ThemedText type="pieMedio" themeColor="onPrimary">
                {i + 1}
              </ThemedText>
            </View>
            <Cadena id={p.cadena} />
          </View>
        </Marker>
      ))}
    </MapView>
  );
}

const styles = StyleSheet.create({
  parada: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingLeft: Spacing.one,
    paddingRight: 10,
    paddingVertical: Spacing.one,
    borderRadius: Radius.pill,
  },
  numero: {
    width: 22,
    height: 22,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
