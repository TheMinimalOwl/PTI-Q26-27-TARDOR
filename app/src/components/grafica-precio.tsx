import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { formatoPrecio } from '@/utils/formato';
import { useTheme } from '@/hooks/use-theme';

type Props = {
  valores: number[];
  /** Precios con línea guía y etiqueta a la derecha (p. ej. [8, 4]). */
  guias: number[];
  /** Tres etiquetas del eje: inicio, mitad y final. */
  eje: [string, string, string];
  maximo: { precio: number; mes: string };
  alto: number;
};

const ANCHO_ETIQUETAS = 28;
const MARGEN_SUPERIOR = 34;
const MARGEN_INFERIOR = 44;
const GROSOR = 2;

/** Una línea, sin relleno, con el máximo anotado. Dibujada con Views para no añadir librerías. */
export function GraficaPrecio({ valores, guias, eje, maximo, alto }: Props) {
  const theme = useTheme();
  const [ancho, setAncho] = useState(0);
  const anchoLinea = Math.max(ancho - ANCHO_ETIQUETAS, 0);

  const min = Math.min(...valores, ...guias);
  const max = Math.max(...valores, ...guias);
  const alturaUtil = alto - MARGEN_SUPERIOR - MARGEN_INFERIOR;
  const y = (v: number) => MARGEN_SUPERIOR + ((max - v) / (max - min)) * alturaUtil;
  const x = (i: number) => (i / (valores.length - 1)) * anchoLinea;
  const base = alto - 24;
  const iMax = valores.indexOf(Math.max(...valores));

  return (
    <View
      accessible
      accessibilityLabel={`Gráfica de precio. Máximo ${formatoPrecio(maximo.precio)} en ${maximo.mes}. Hoy ${formatoPrecio(valores[valores.length - 1])}.`}
      onLayout={(e) => setAncho(e.nativeEvent.layout.width)}
      style={{ height: alto }}>
      {ancho > 0 && (
        <>
          {guias.map((g) => (
            <View
              key={g}
              style={[
                styles.guia,
                { top: y(g), width: anchoLinea, backgroundColor: theme.hairline },
              ]}>
              <ThemedText
                type="nota"
                numberOfLines={1}
                style={[styles.etiquetaGuia, { left: anchoLinea + 6 }]}>
                {`${g} €`}
              </ThemedText>
            </View>
          ))}
          <View
            style={[styles.guia, { top: base, width: anchoLinea, backgroundColor: theme.hairline }]}
          />

          {valores.slice(1).map((v, i) => {
            const x1 = x(i);
            const y1 = y(valores[i]);
            const dx = x(i + 1) - x1;
            const dy = y(v) - y1;
            const largo = Math.hypot(dx, dy);
            return (
              <View
                key={i}
                style={[
                  styles.tramo,
                  {
                    left: x1 + dx / 2 - largo / 2,
                    top: y1 + dy / 2 - GROSOR / 2,
                    width: largo + GROSOR / 2,
                    backgroundColor: theme.icon,
                    transform: [{ rotate: `${Math.atan2(dy, dx)}rad` }],
                  },
                ]}
              />
            );
          })}

          <View
            style={[
              styles.punto,
              { left: x(iMax) - 4, top: y(maximo.precio) - 4, backgroundColor: theme.icon },
            ]}
          />
          <ThemedText
            type="nota"
            themeColor="text"
            style={[styles.anotacion, { left: x(iMax) + 12, top: y(maximo.precio) - 18 }]}>
            {`Máximo: ${formatoPrecio(maximo.precio)} · ${maximo.mes}`}
          </ThemedText>

          <ThemedText type="nota" style={[styles.eje, { top: base + 6, left: 0 }]}>
            {eje[0]}
          </ThemedText>
          <ThemedText
            type="nota"
            style={[styles.eje, styles.centro, { top: base + 6, left: anchoLinea / 2 - 30 }]}>
            {eje[1]}
          </ThemedText>
          <ThemedText
            type="nota"
            style={[styles.eje, styles.derecha, { top: base + 6, left: anchoLinea - 60 }]}>
            {eje[2]}
          </ThemedText>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  guia: { position: 'absolute', left: 0, height: 1 },
  etiquetaGuia: { position: 'absolute', top: -7, width: ANCHO_ETIQUETAS - 6 },
  tramo: { position: 'absolute', height: GROSOR, borderRadius: GROSOR },
  punto: { position: 'absolute', width: 8, height: 8, borderRadius: 4 },
  anotacion: { position: 'absolute' },
  eje: { position: 'absolute', width: 60 },
  centro: { textAlign: 'center' },
  derecha: { textAlign: 'right' },
});
