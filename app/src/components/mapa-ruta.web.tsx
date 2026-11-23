import { View } from 'react-native';

import type { Parada } from '@/data/ruta';
import { useTheme } from '@/hooks/use-theme';

type Props = { paradas: Parada[]; alto: number };

/**
 * react-native-maps no funciona en web: plano de OpenStreetMap que encuadra todas las paradas.
 * El orden y las direcciones van en la lista de debajo.
 */
export function MapaRuta({ paradas, alto }: Props) {
  const theme = useTheme();
  const puntos = paradas.flatMap((p) => (p.coordenadas ? [p.coordenadas] : []));
  if (puntos.length === 0) {
    return <View style={{ height: alto, backgroundColor: theme.backgroundElement }} />;
  }

  const margen = 0.004;
  const lats = puntos.map((p) => p.latitude);
  const lngs = puntos.map((p) => p.longitude);
  const caja = [
    Math.min(...lngs) - margen,
    Math.min(...lats) - margen,
    Math.max(...lngs) + margen,
    Math.max(...lats) + margen,
  ].join(',');
  const [primera] = puntos;
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${caja}&layer=mapnik&marker=${primera.latitude},${primera.longitude}`;

  return (
    <View style={{ height: alto, backgroundColor: theme.backgroundElement }}>
      <iframe
        title="Plano de la ruta"
        src={src}
        style={{ border: 0, width: '100%', height: '100%' }}
        loading="lazy"
      />
    </View>
  );
}
