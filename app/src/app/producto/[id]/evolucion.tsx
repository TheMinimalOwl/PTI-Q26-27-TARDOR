import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { pistaError } from '@/api/http';
import { serieDesdeHistorial } from '@/api/producto';
import { BotonCompartir } from '@/components/boton-compartir';
import { CeldaAjuste } from '@/components/celda-ajuste';
import { ControlSegmentado } from '@/components/control-segmentado';
import { EstadoVacio } from '@/components/estado-vacio';
import { FilaDato } from '@/components/fila-dato';
import { GraficaPrecio } from '@/components/grafica-precio';
import { PantallaDetalle } from '@/components/pantalla-detalle';
import { ThemedText } from '@/components/themed-text';
import { useFicha } from '@/data/ficha';
import { useEscritorio } from '@/hooks/use-web';
import { formatoPrecio, nombreCadena } from '@/utils/formato';
import { haceMeses } from '@/utils/meses';

const periodos = ['6 meses', '2 años'] as const;
type Periodo = (typeof periodos)[number];
const MESES: Record<Periodo, number> = { '6 meses': 6, '2 años': 24 };

/** C2 · Evolución del precio (datos de prueba o historial de la API). */
export default function Evolucion() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const ficha = useFicha(id, { comparar: false });
  const escritorio = useEscritorio();
  const [periodo, setPeriodo] = useState<Periodo>('2 años');
  const [aviso, setAviso] = useState(true);

  if (ficha.estado !== 'ok' || ficha.datos === null) {
    return (
      <PantallaDetalle>
        {ficha.estado === 'cargando' ? (
          <ThemedText type="pie">Cargando historial…</ThemedText>
        ) : ficha.estado === 'error' ? (
          <EstadoVacio
            titulo="No hemos podido cargar el historial"
            texto={`${ficha.mensaje}. ${pistaError}`}
            accion={{ etiqueta: 'Reintentar', onPress: ficha.reintentar }}
          />
        ) : (
          <EstadoVacio titulo="Aún no tenemos este producto" texto="No hay historial que enseñar." />
        )}
      </PantallaDetalle>
    );
  }

  const producto = ficha.datos;
  const ultimo = producto.puntos[producto.puntos.length - 1]?.observed_on;
  const serie = serieDesdeHistorial(
    producto.puntos,
    ultimo ? haceMeses(ultimo, MESES[periodo]) : undefined,
  );

  return (
    <PantallaDetalle>
      <Stack.Screen
        options={{
          title: 'Evolución del precio',
          headerBackTitle: producto.nombre.split(' ')[0],
          headerRight: () =>
            producto.mejor ? (
              <BotonCompartir
                mensaje={`${producto.nombre}: ${formatoPrecio(producto.mejor.precio)} hoy`}
              />
            ) : null,
        }}
      />

      {escritorio && <ThemedText type="display">Evolución del precio</ThemedText>}
      <View style={styles.producto}>
        <ThemedText type="cuerpo15Medio">{producto.nombreCompleto}</ThemedText>
        <ThemedText type="pie">{producto.subtituloEvolucion}</ThemedText>
      </View>

      <ControlSegmentado opciones={periodos} seleccionada={periodo} onCambiar={setPeriodo} />

      {serie ? (
        <>
          <GraficaPrecio
            valores={serie.valores}
            guias={serie.guias}
            eje={serie.eje}
            maximo={serie.maximo}
            alto={escritorio ? 320 : 220}
          />
          <View>
            {producto.mejor && (
              <FilaDato
                etiqueta="Hoy"
                detalle={nombreCadena(producto.mejor.cadena)}
                valor={producto.mejor.precio}
              />
            )}
            <FilaDato etiqueta="Máximo" detalle={serie.maximo.mes} valor={serie.maximo.precio} />
            <FilaDato etiqueta={`Media de ${periodo}`} valor={serie.media} />
          </View>
        </>
      ) : (
        <EstadoVacio
          titulo="Aún no hay historial"
          texto="Este producto tiene menos de dos precios en este periodo."
        />
      )}

      {producto.avisoBajoDe !== undefined && (
        <CeldaAjuste
          icono="campana"
          etiqueta={`Avisarme si baja de ${formatoPrecio(producto.avisoBajoDe)}`}
          activado={aviso}
          onCambiar={setAviso}
        />
      )}
    </PantallaDetalle>
  );
}

const styles = StyleSheet.create({
  producto: { gap: 2 },
});
