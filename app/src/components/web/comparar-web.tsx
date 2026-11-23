import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import type { ResumenCesta } from '@/api/adaptadores';
import { Boton } from '@/components/boton';
import { Cadena } from '@/components/cadena';
import { FotoProducto } from '@/components/foto-producto';
import { ThemedText } from '@/components/themed-text';
import { PaginaWeb } from '@/components/web/pagina-web';
import { Celda, FilaTabla, PrecioCelda, TituloColumna } from '@/components/web/tabla';
import { Cadenas, Spacing } from '@/constants/theme';
import { textoFalta } from '@/data/cesta';
import { inicio, nombreLista, type ProductoLista } from '@/data/datos-ejemplo';
import { formatoPrecio, nombreCadena, plural } from '@/utils/formato';

const ANCHO_CADENA = 100;

type Props = { resumen: ResumenCesta; lista: ProductoLista[] };

/** W4 · Comparar cesta a 1440: cada producto en cada cadena, totales y la opción de repartir. */
export function CompararWeb({ resumen, lista }: Props) {
  const { completas, incompletas, repartida, productos } = resumen;
  const cestas = [...completas, ...incompletas];
  // Columnas: las 8 cadenas en su orden fijo y después las que la API traiga y la app no conozca.
  const columnas = [
    ...Cadenas.map((c) => c.id as string),
    ...cestas.map((c) => c.cadena).filter((c) => !Cadenas.some((x) => x.id === c)),
  ];
  const cestaDe = (cadena: string) => cestas.find((c) => c.cadena === cadena);
  const mejor = completas[0];

  return (
    <PaginaWeb>
      <View>
        <ThemedText type="display">Comparar cesta</ThemedText>
        <ThemedText type="cuerpo15" themeColor="textSecondary">
          {`${nombreLista} · ${plural(lista.length, 'producto')} · ${inicio.tituloWeb.replace('Precios', 'precios')}`}
        </ThemedText>
      </View>

      <View>
        <FilaTabla cabecera>
          <Celda cabecera>
            <TituloColumna>Producto</TituloColumna>
          </Celda>
          {columnas.map((c) => (
            <Celda key={c} cabecera derecha ancho={ANCHO_CADENA}>
              <Cadena id={c} pequena />
            </Celda>
          ))}
        </FilaTabla>

        {lista.map((p) => {
          const precios = columnas.map((c) => cestaDe(c)?.precios[p.id]);
          const definidos = precios.filter((v): v is number => v !== undefined);
          const minimo = definidos.length ? Math.min(...definidos) : undefined;
          return (
            <FilaTabla key={p.id}>
              <Celda>
                <FotoProducto formato={p.formato} tamano={48} />
                <View style={styles.texto}>
                  <ThemedText type="cuerpo15Medio">{p.nombre}</ThemedText>
                  <ThemedText type="pie">
                    {p.cantidad > 1 ? `${p.cantidad} × ${p.formato}` : p.formato}
                  </ThemedText>
                </View>
              </Celda>
              {precios.map((precio, i) => {
                const esMejor = precio !== undefined && precio === minimo;
                return (
                  <Celda key={columnas[i]} derecha ancho={ANCHO_CADENA} mejor={esMejor}>
                    <PrecioCelda
                      texto={precio !== undefined ? formatoPrecio(precio) : undefined}
                      mejor={esMejor}
                    />
                  </Celda>
                );
              })}
            </FilaTabla>
          );
        })}

        <FilaTabla total>
          <Celda>
            <ThemedText type="titular">Total</ThemedText>
          </Celda>
          {columnas.map((c) => {
            const cesta = cestaDe(c);
            const completa = cesta && cesta.falta.length === 0;
            const esMejor = mejor?.cadena === c;
            return (
              <Celda key={c} derecha ancho={ANCHO_CADENA} mejor={esMejor}>
                {completa ? (
                  <ThemedText type="precio17" themeColor={esMejor ? 'onTint' : 'text'}>
                    {formatoPrecio(cesta.total)}
                  </ThemedText>
                ) : (
                  // Cesta incompleta: «x de 5» en vez del total, que engañaría.
                  <View style={styles.incompleta}>
                    <ThemedText type="pie">—</ThemedText>
                    <ThemedText type="nota">
                      {cesta ? textoFalta(cesta.falta.length) : `faltan ${productos}`}
                    </ThemedText>
                  </View>
                )}
              </Celda>
            );
          })}
        </FilaTabla>
      </View>

      <View style={styles.resumen}>
        <View style={styles.bloque}>
          <ThemedText type="pieMedio" themeColor="textSecondary">
            Todo en una tienda
          </ThemedText>
          {mejor ? (
            <View style={styles.donde}>
              <ThemedText type="precio22" themeColor="text">
                {formatoPrecio(mejor.total)}
              </ThemedText>
              <ThemedText type="cuerpo15" themeColor="textSecondary">
                en
              </ThemedText>
              <Cadena id={mejor.cadena} />
            </View>
          ) : (
            <ThemedText type="cuerpo15">Ninguna cadena tiene toda la lista</ThemedText>
          )}
        </View>
        <View style={styles.bloque}>
          <ThemedText type="pieMedio" themeColor="textSecondary">
            {`Repartida en ${plural(repartida.tiendas.length, 'tienda')}`}
          </ThemedText>
          <ThemedText type="precio22" themeColor="text">
            {formatoPrecio(repartida.total)}
          </ThemedText>
          {repartida.ahorro !== null && repartida.ahorro > 0 && (
            <ThemedText type="pie">
              {`Ahorras ${formatoPrecio(repartida.ahorro)} con ${plural(repartida.tiendas.length, 'visita')}`}
            </ThemedText>
          )}
        </View>
        <View style={styles.espacio} />
        {mejor ? (
          <Boton
            etiqueta={`Cómo llegar a ${nombreCadena(mejor.cadena)}`}
            onPress={() => router.push({ pathname: '/ruta', params: { cadena: mejor.cadena } })}
          />
        ) : (
          <Boton etiqueta="Ver la ruta repartida" onPress={() => router.push('/ruta')} />
        )}
      </View>
    </PaginaWeb>
  );
}

const styles = StyleSheet.create({
  texto: { flex: 1, gap: 2 },
  incompleta: { alignItems: 'flex-end' },
  resumen: { flexDirection: 'row', alignItems: 'center', gap: Spacing.four },
  bloque: { width: 384, gap: Spacing.one },
  donde: { flexDirection: 'row', alignItems: 'baseline', gap: Spacing.two },
  espacio: { flex: 1 },
});
