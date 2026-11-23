import { router, Stack } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import type { ResumenCesta } from '@/api/adaptadores';
import { pistaError } from '@/api/http';
import { Boton } from '@/components/boton';
import { BotonCompartir } from '@/components/boton-compartir';
import { CabeceraSeccion } from '@/components/cabecera-seccion';
import { ControlSegmentado } from '@/components/control-segmentado';
import { EstadoVacio } from '@/components/estado-vacio';
import { FilaDato } from '@/components/fila-dato';
import { FilaPrecio } from '@/components/fila-precio';
import { PantallaDetalle } from '@/components/pantalla-detalle';
import { ThemedText } from '@/components/themed-text';
import { CompararWeb } from '@/components/web/comparar-web';
import { distanciaA, textoFalta, textoRepartida, useCesta } from '@/data/cesta';
import { nombreLista, type ProductoLista } from '@/data/datos-ejemplo';
import { useEscritorio } from '@/hooks/use-web';
import { formatoPrecio, nombreCadena, plural } from '@/utils/formato';

const vistas = ['En una tienda', 'Repartida'] as const;

/** E2 · Comparar cesta (W4 en la web ancha) */
export default function Comparar() {
  const cesta = useCesta();
  const escritorio = useEscritorio();

  if (cesta.lista.length === 0 || cesta.estado !== 'ok') {
    return (
      <PantallaDetalle>
        {cesta.lista.length === 0 ? (
          <EstadoVacio
            titulo="Tu lista está vacía"
            texto="Añade productos para comparar dónde sale más barata."
            accion={{ etiqueta: 'Buscar productos', onPress: () => router.push('/screens/buscar') }}
          />
        ) : cesta.estado === 'error' ? (
          <EstadoVacio
            titulo="No hemos podido comparar la lista"
            texto={`${cesta.mensaje}. ${pistaError}`}
            accion={{ etiqueta: 'Reintentar', onPress: cesta.reintentar }}
          />
        ) : (
          <ThemedText type="pie">Comparando la lista en las cadenas…</ThemedText>
        )}
      </PantallaDetalle>
    );
  }

  return escritorio ? (
    <CompararWeb resumen={cesta.datos} lista={cesta.lista} />
  ) : (
    <CompararMovil resumen={cesta.datos} lista={cesta.lista} />
  );
}

function CompararMovil({ resumen, lista }: { resumen: ResumenCesta; lista: ProductoLista[] }) {
  const [vista, setVista] = useState<(typeof vistas)[number]>('En una tienda');
  const { completas, incompletas, repartida, productos } = resumen;
  const mejor = completas[0];
  const nombre = (id: string) => lista.find((p) => p.id === id)?.nombre ?? id;

  return (
    <PantallaDetalle
      pie={
        vista === 'En una tienda' && mejor ? (
          <Boton
            etiqueta={`Cómo llegar a ${nombreCadena(mejor.cadena)}`}
            onPress={() => router.push({ pathname: '/ruta', params: { cadena: mejor.cadena } })}
          />
        ) : (
          <Boton
            etiqueta={`Ver ruta por las ${plural(repartida.tiendas.length, 'tienda')}`}
            onPress={() => router.push('/ruta')}
          />
        )
      }>
      {mejor && (
        <Stack.Screen
          options={{
            headerRight: () => (
              <BotonCompartir
                mensaje={`${nombreLista}: ${formatoPrecio(mejor.total)} en ${nombreCadena(mejor.cadena)}`}
              />
            ),
          }}
        />
      )}

      <ControlSegmentado opciones={vistas} seleccionada={vista} onCambiar={setVista} />

      {vista === 'En una tienda' ? (
        <>
          <View>
            <CabeceraSeccion titulo="Tienen toda tu lista" />
            {completas.length === 0 && (
              <ThemedText type="pie">Ninguna cadena tiene todos los productos.</ThemedText>
            )}
            {completas.map((fila, i) => (
              <FilaPrecio
                key={fila.cadena}
                cadena={fila.cadena}
                mejor={i === 0}
                detalle={[`${fila.tiene} de ${productos}`, distanciaA(fila.cadena)]
                  .filter(Boolean)
                  .join(' · ')}
                valor={formatoPrecio(fila.total)}
                nota={i === 0 ? 'Más barato' : `+${formatoPrecio(fila.diferencia)}`}
              />
            ))}
          </View>

          {incompletas.length > 0 && (
            <View>
              <CabeceraSeccion titulo="Les falta algo" />
              {incompletas.map((fila) => (
                <FilaPrecio
                  key={fila.cadena}
                  apagada
                  cadena={fila.cadena}
                  detalle={distanciaA(fila.cadena)}
                  valor={`${fila.tiene} de ${productos}`}
                  nota={`${formatoPrecio(fila.total)} · ${textoFalta(fila.falta.length)}`}
                />
              ))}
            </View>
          )}

          {mejor && (
            <View>
              <CabeceraSeccion titulo={`En ${nombreCadena(mejor.cadena)}`} />
              {Object.entries(mejor.precios).map(([id, precio]) => (
                <FilaDato
                  key={id}
                  etiqueta={mejor.productos[id] ?? nombre(id)}
                  valor={precio}
                />
              ))}
            </View>
          )}
        </>
      ) : (
        <>
          <ThemedText type="pie">{textoRepartida(resumen)}</ThemedText>
          {repartida.tiendas.map((t) => (
            <View key={t.cadena}>
              <CabeceraSeccion titulo={`En ${nombreCadena(t.cadena)}`} />
              {Object.entries(t.precios).map(([id, precio]) => (
                <FilaDato key={id} etiqueta={t.productos[id] ?? nombre(id)} valor={precio} />
              ))}
            </View>
          ))}
        </>
      )}
    </PantallaDetalle>
  );
}
