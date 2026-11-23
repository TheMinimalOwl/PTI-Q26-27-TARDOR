import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { pistaError } from '@/api/http';
import { Cadena } from '@/components/cadena';
import { CampoBusqueda } from '@/components/campo-busqueda';
import { Chip } from '@/components/chip';
import { EstadoVacio } from '@/components/estado-vacio';
import { FotoProducto } from '@/components/foto-producto';
import { OpcionSeleccionable } from '@/components/opcion-seleccionable';
import { ThemedText } from '@/components/themed-text';
import { PaginaWeb } from '@/components/web/pagina-web';
import { Celda, FilaTabla, PrecioCelda, TituloColumna } from '@/components/web/tabla';
import { Cadenas, Spacing, type CadenaId } from '@/constants/theme';
import { MINIMO_LETRAS, preciosPorCadenaDe, textoRecuento, useBusqueda } from '@/data/busqueda';
import { busqueda, filtros, type ProductoCatalogo } from '@/data/datos-ejemplo';
import { filtrosIniciales, setFiltros, useFiltros } from '@/data/estado-filtros';
import { esCadenaConocida, formatoPrecio, nombreCadena, plural } from '@/utils/formato';

const ANCHO_PRODUCTO = 296;
const ANCHO_CADENA = 80;

type Props = { consulta: string; onCambiar: (texto: string) => void };

/** W2 · Buscar a 1440: filtros en columna lateral y tabla con una columna por cadena. */
export function BuscarWeb({ consulta, onCambiar }: Props) {
  const { orden, cadenas } = useFiltros();
  const resultado = useBusqueda(consulta);
  const filtradas = Cadenas.length - cadenas.length;

  const alternarCadena = (id: CadenaId) =>
    setFiltros((f) => ({
      ...f,
      cadenas: f.cadenas.includes(id) ? f.cadenas.filter((c) => c !== id) : [...f.cadenas, id],
    }));

  return (
    <PaginaWeb>
      <View style={styles.columnas}>
        <View style={styles.filtros}>
          <ThemedText type="titular">Filtros</ThemedText>
          <EtiquetaFiltro texto="Ordenar por" />
          {filtros.ordenes.map((o) => (
            <OpcionSeleccionable
              key={o}
              etiqueta={o}
              marcada={o === orden}
              onPress={() => setFiltros((f) => ({ ...f, orden: o }))}
            />
          ))}
          <EtiquetaFiltro texto="Cadenas" />
          {Cadenas.map((c) => (
            <OpcionSeleccionable
              key={c.id}
              etiqueta={c.nombre}
              marcada={cadenas.includes(c.id)}
              onPress={() => alternarCadena(c.id)}
            />
          ))}
        </View>

        <View style={styles.resultados}>
          <CampoBusqueda valor={consulta} onChangeText={onCambiar} autoFocus />
          <View style={styles.activos}>
            {filtradas > 0 && (
              <Chip
                activo
                etiqueta={`Sin ${plural(filtradas, 'cadena')}`}
                onPress={() => setFiltros((f) => ({ ...f, cadenas: filtrosIniciales.cadenas }))}
              />
            )}
            {resultado.estado === 'ok' && (
              <ThemedText type="pie">
                {`${textoRecuento(resultado.datos.productos.length, resultado.datos.total, resultado.datos.parecidos)} · por ${orden.toLowerCase()}`}
              </ThemedText>
            )}
            {resultado.estado === 'cargando' && consulta.trim().length >= MINIMO_LETRAS && (
              <ThemedText type="pie">{busqueda.cargando.texto}</ThemedText>
            )}
          </View>
          <Tabla consulta={consulta} resultado={resultado} />
        </View>
      </View>
    </PaginaWeb>
  );
}

function EtiquetaFiltro({ texto }: { texto: string }) {
  return (
    <ThemedText type="pieMedio" themeColor="textSecondary" style={styles.etiqueta}>
      {texto}
    </ThemedText>
  );
}

function Tabla({
  consulta,
  resultado,
}: {
  consulta: string;
  resultado: ReturnType<typeof useBusqueda>;
}) {
  if (consulta.trim().length < MINIMO_LETRAS) {
    return (
      <EstadoVacio titulo="Busca un producto" texto="Escribe al menos dos letras del nombre o la marca." />
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
  if (resultado.estado === 'ok' && resultado.datos.productos.length === 0) {
    return (
      <EstadoVacio
        titulo={`Nada con «${consulta.trim()}»`}
        texto="Prueba con otra palabra o marca, o marca más cadenas en los filtros."
        accion={{ etiqueta: 'Preguntar al asistente', onPress: () => router.push('/preguntar') }}
      />
    );
  }

  return (
    <View>
      <FilaTabla cabecera>
        <Celda cabecera ancho={ANCHO_PRODUCTO}>
          <TituloColumna>Producto</TituloColumna>
        </Celda>
        {Cadenas.map((c) => (
          <Celda key={c.id} cabecera estrecha derecha ancho={ANCHO_CADENA}>
            <Cadena id={c.id} pequena />
          </Celda>
        ))}
      </FilaTabla>
      {resultado.estado === 'cargando'
        ? [0, 1, 2, 3].map((i) => <FilaCargando key={i} />)
        : resultado.datos.productos.map((p) => <FilaResultado key={p.id} producto={p} />)}
    </View>
  );
}

function FilaResultado({ producto }: { producto: ProductoCatalogo }) {
  const precios = preciosPorCadenaDe(producto);
  const valores = Object.values(precios);
  // El tinte marca la cadena más barata cuando hay con qué comparar.
  const minimo = valores.length > 1 ? Math.min(...valores) : undefined;
  const otras = Object.keys(precios).filter((c) => !esCadenaConocida(c));

  return (
    <FilaTabla
      etiqueta={producto.nombre}
      onPress={() => router.push({ pathname: '/producto/[id]', params: { id: producto.id } })}>
      <Celda ancho={ANCHO_PRODUCTO}>
        {producto.formato ? <FotoProducto formato={producto.formato} tamano={48} /> : null}
        <View style={styles.texto}>
          <ThemedText type="cuerpo15Medio">{producto.nombre}</ThemedText>
          <ThemedText type="pie">
            {[producto.formato, producto.precioUnidad].filter(Boolean).join(' · ')}
          </ThemedText>
          {otras.map((c) => (
            <ThemedText key={c} type="pie">{`${formatoPrecio(precios[c])} en ${nombreCadena(c)}`}</ThemedText>
          ))}
        </View>
      </Celda>
      {Cadenas.map((c) => {
        const precio = precios[c.id];
        const mejor = precio !== undefined && precio === minimo;
        return (
          <Celda key={c.id} estrecha derecha mejor={mejor} ancho={ANCHO_CADENA}>
            <PrecioCelda texto={precio !== undefined ? formatoPrecio(precio) : undefined} mejor={mejor} />
          </Celda>
        );
      })}
    </FilaTabla>
  );
}

function FilaCargando() {
  return (
    <FilaTabla>
      <Celda>
        <ThemedText type="pie">…</ThemedText>
      </Celda>
    </FilaTabla>
  );
}

const styles = StyleSheet.create({
  columnas: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.four },
  filtros: { width: 240 },
  etiqueta: { paddingTop: Spacing.three, paddingBottom: Spacing.one },
  resultados: { flex: 1, gap: Spacing.three },
  activos: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two, minHeight: 36 },
  texto: { flex: 1, gap: 2 },
});
