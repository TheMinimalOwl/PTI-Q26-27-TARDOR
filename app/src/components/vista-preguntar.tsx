import { router } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { esIdApi } from '@/api/cliente';
import type { FuenteRespuesta } from '@/api/rag';
import { Aviso } from '@/components/aviso';
import { Cadena } from '@/components/cadena';
import { FilaPrecio } from '@/components/fila-precio';
import { Icono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { Celda, FilaTabla, TituloColumna } from '@/components/web/tabla';
import { Fonts, SinContornoWeb, MaxContentWidth, Radius, Spacing, Web } from '@/constants/theme';
import { resumenDePrueba, textoRepartida } from '@/data/cesta';
import { preguntar } from '@/data/datos-ejemplo';
import { useLista } from '@/data/estado-lista';
import { usePreguntar, type Mensaje } from '@/data/preguntar';
import { useTheme } from '@/hooks/use-theme';
import { formatoPrecio, formatoPrecioUnidad, nombreCadena } from '@/utils/formato';

type Props = {
  /** D2 forzado (`?sinConexion=1`): sin conversación, solo el aviso y la pista. */
  sinConexion?: boolean;
  /** Espacio extra abajo (la barra de pestañas cuando va dentro de Buscar). */
  margenInferior?: number;
  /** W5: columna de lectura de 720 con título, tablas y el campo debajo de la conversación. */
  escritorio?: boolean;
};

/** D1 · Preguntar. Las respuestas no van en burbuja: son texto y filas normales. */
export function VistaPreguntar({ sinConexion: forzar = false, margenInferior = 0, escritorio }: Props) {
  const conversacion = usePreguntar(forzar);
  const { mensajes, sinConexion, conEjemplo } = conversacion;

  const contenido = (
    <>
      {escritorio && (
        <View style={styles.titulo}>
          <ThemedText type="display">Preguntar</ThemedText>
          <ThemedText type="cuerpo15" themeColor="textSecondary">
            Responde con los precios leídos hoy. Si no lo sabe, lo dice.
          </ThemedText>
        </View>
      )}
      {sinConexion ? (
        <>
          <Aviso
            icono="sinConexion"
            titulo={preguntar.sinConexion.titulo}
            texto={preguntar.sinConexion.texto}
            accion={{ etiqueta: 'Reintentar', onPress: conversacion.reintentarConexion }}
          />
          <Pista />
        </>
      ) : (
        <>
          {conEjemplo && <Ejemplo escritorio={escritorio} />}
          {!conEjemplo && mensajes.length === 0 && <Pista />}
          {mensajes.map((m) => (
            <View key={m.id} style={styles.intercambio}>
              <Burbuja texto={m.pregunta} />
              <RespuestaMensaje
                mensaje={m}
                escritorio={escritorio}
                onReintentar={() => conversacion.enviar(m.pregunta)}
              />
            </View>
          ))}
        </>
      )}
    </>
  );

  const campo = (
    <CampoPregunta
      deshabilitado={sinConexion || conversacion.ocupado}
      onEnviar={conversacion.enviar}
    />
  );

  if (escritorio) {
    return (
      <View style={styles.columnaWeb}>
        {contenido}
        <View style={styles.campoWeb}>{campo}</View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.raiz}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        style={styles.raiz}
        contentContainerStyle={styles.contenido}
        keyboardDismissMode="interactive">
        <View style={styles.columna}>{contenido}</View>
      </ScrollView>
      <BarraEscribir margenInferior={margenInferior}>{campo}</BarraEscribir>
    </KeyboardAvoidingView>
  );
}

function Pista() {
  return (
    <View style={styles.pista}>
      <ThemedText type="titular">{preguntar.vacio.titulo}</ThemedText>
      <ThemedText type="cuerpo15" themeColor="textSecondary">
        {preguntar.vacio.texto}
      </ThemedText>
    </View>
  );
}

function Burbuja({ texto }: { texto: string }) {
  const theme = useTheme();
  return (
    <View style={[styles.burbuja, { backgroundColor: theme.backgroundElement }]}>
      <ThemedText type="cuerpo15">{texto}</ThemedText>
    </View>
  );
}

function Enlace({ texto, onPress }: { texto: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="link" hitSlop={12} onPress={onPress}>
      <ThemedText type="pieMedio" themeColor="link" style={styles.subrayado}>
        {texto}
      </ThemedText>
    </Pressable>
  );
}

/** Conversación de ejemplo de Figma (datos de prueba), calculada con la lista actual. */
function Ejemplo({ escritorio }: { escritorio?: boolean }) {
  const lista = useLista();
  const resumen = resumenDePrueba(lista);
  const mejores = resumen.completas.slice(0, 3);
  if (mejores.length === 0) return null;

  return (
    <View style={styles.intercambio}>
      <Burbuja texto={preguntar.pregunta} />
      <View style={styles.respuesta}>
        <ThemedText type="cuerpo">
          {`Con los precios de hoy, tus ${resumen.productos} productos salen más baratos todos juntos en ${nombreCadena(mejores[0].cadena)}.`}
        </ThemedText>
        {escritorio ? (
          <View>
            <FilaTabla cabecera>
              <Celda cabecera>
                <TituloColumna>Cadena</TituloColumna>
              </Celda>
              <Celda cabecera derecha ancho={140}>
                <TituloColumna>Productos</TituloColumna>
              </Celda>
              <Celda cabecera derecha ancho={140}>
                <TituloColumna>Total</TituloColumna>
              </Celda>
            </FilaTabla>
            {mejores.map((c, i) => (
              <FilaTabla key={c.cadena} mejor={i === 0}>
                <Celda>
                  <Cadena id={c.cadena} />
                </Celda>
                <Celda derecha ancho={140}>
                  <ThemedText type="pie" themeColor={i === 0 ? 'onTint' : 'textSecondary'}>
                    {`${c.tiene} de ${resumen.productos}`}
                  </ThemedText>
                </Celda>
                <Celda derecha ancho={140}>
                  <ThemedText type="precio15" themeColor={i === 0 ? 'onTint' : 'text'}>
                    {formatoPrecio(c.total)}
                  </ThemedText>
                </Celda>
              </FilaTabla>
            ))}
          </View>
        ) : (
          <View>
            {mejores.map((c, i) => (
              <FilaPrecio
                key={c.cadena}
                cadena={c.cadena}
                mejor={i === 0}
                detalle={`${c.tiene} de ${resumen.productos} productos`}
                valor={formatoPrecio(c.total)}
                nota={i === 0 ? 'Más barato' : `+${formatoPrecio(c.diferencia)}`}
              />
            ))}
          </View>
        )}
        <ThemedText type="cuerpo">{`${textoRepartida(resumen)}.`}</ThemedText>
        <View style={styles.enlaces}>
          {!escritorio && <Enlace texto="Ver reparto" onPress={() => router.push('/ruta')} />}
          <Enlace
            texto={escritorio ? 'Abrir comparación de la cesta' : 'Abrir comparación'}
            onPress={() => router.push('/comparar')}
          />
        </View>
        <ThemedText type="nota">{preguntar.fuente}</ThemedText>
      </View>
    </View>
  );
}

function RespuestaMensaje({
  mensaje,
  escritorio,
  onReintentar,
}: {
  mensaje: Mensaje;
  escritorio?: boolean;
  onReintentar: () => void;
}) {
  if (mensaje.estado === 'error') {
    return (
      <Aviso
        icono="alerta"
        titulo="El asistente no ha podido responder"
        texto={mensaje.error ?? 'Inténtalo de nuevo en un momento.'}
        accion={{ etiqueta: 'Reintentar', onPress: onReintentar }}
      />
    );
  }
  if (mensaje.estado === 'esperando') {
    return mensaje.parcial ? (
      <ThemedText type="cuerpo">{mensaje.parcial}</ThemedText>
    ) : (
      <ThemedText type="pie">Buscando en los precios de hoy…</ThemedText>
    );
  }

  const r = mensaje.respuesta!;
  return (
    <View style={styles.respuesta}>
      <ThemedText type="cuerpo">{r.texto}</ThemedText>
      {r.abstenida && (
        <ThemedText type="pie">No lo he encontrado en los precios que tenemos hoy.</ThemedText>
      )}
      {r.fuentes.length > 0 && <Fuentes fuentes={r.fuentes} escritorio={escritorio} />}
      {r.avisos.length > 0 && (
        <ThemedText type="nota">{`Revisa la respuesta: ${r.avisos.join(' ')}`}</ThemedText>
      )}
      <ThemedText type="nota">Respuesta del asistente con los precios del catálogo.</ThemedText>
    </View>
  );
}

/**
 * Productos citados. El asistente lee el catálogo de la API, así que sus ids son los de la API y
 * abren la ficha; un id que no lo sea (índice local del asistente) abre Buscar con el nombre.
 */
function Fuentes({ fuentes, escritorio }: { fuentes: FuenteRespuesta[]; escritorio?: boolean }) {
  const abrir = (f: FuenteRespuesta) =>
    esIdApi(f.id)
      ? router.push({ pathname: '/producto/[id]', params: { id: f.id } })
      : router.push({ pathname: '/screens/buscar', params: { q: f.nombre } });

  if (!escritorio) {
    return (
      <View>
        {fuentes.map((f) => (
          <Pressable key={f.id} accessibilityRole="link" onPress={() => abrir(f)}>
            <FilaPrecio
              cadena={f.cadena}
              detalle={f.nombre}
              valor={f.precio != null ? formatoPrecio(f.precio) : undefined}
              nota={formatoPrecioUnidad(f.precioUnidad, f.unidad) || undefined}
            />
          </Pressable>
        ))}
      </View>
    );
  }
  return (
    <View>
      <FilaTabla cabecera>
        <Celda cabecera>
          <TituloColumna>Producto</TituloColumna>
        </Celda>
        <Celda cabecera ancho={140}>
          <TituloColumna>Cadena</TituloColumna>
        </Celda>
        <Celda cabecera derecha ancho={110}>
          <TituloColumna>Por unidad</TituloColumna>
        </Celda>
        <Celda cabecera derecha ancho={90}>
          <TituloColumna>Precio</TituloColumna>
        </Celda>
      </FilaTabla>
      {fuentes.map((f) => (
        <FilaTabla key={f.id} etiqueta={f.nombre} onPress={() => abrir(f)}>
          <Celda>
            <ThemedText type="cuerpo15Medio">{f.nombre}</ThemedText>
          </Celda>
          <Celda ancho={140}>
            <Cadena id={f.cadena} />
          </Celda>
          <Celda derecha ancho={110}>
            <ThemedText type="pie">{formatoPrecioUnidad(f.precioUnidad, f.unidad) || '—'}</ThemedText>
          </Celda>
          <Celda derecha ancho={90}>
            <ThemedText type="precio15">
              {f.precio != null ? formatoPrecio(f.precio) : '—'}
            </ThemedText>
          </Celda>
        </FilaTabla>
      ))}
    </View>
  );
}

function CampoPregunta({
  deshabilitado,
  onEnviar,
}: {
  deshabilitado: boolean;
  onEnviar: (texto: string) => void;
}) {
  const theme = useTheme();
  const [texto, setTexto] = useState('');
  const puedeEnviar = texto.trim().length > 0 && !deshabilitado;

  const enviar = () => {
    if (!puedeEnviar) return;
    onEnviar(texto);
    setTexto('');
  };

  return (
    <View style={styles.filaEscribir}>
      <View style={[styles.campo, { backgroundColor: theme.backgroundElement }]}>
        <TextInput
          value={texto}
          onChangeText={setTexto}
          onSubmitEditing={enviar}
          placeholder="Escribe una pregunta"
          placeholderTextColor={theme.textSecondary}
          returnKeyType="send"
          accessibilityLabel="Escribe una pregunta"
          style={[styles.entrada, { color: theme.text }]}
        />
        {Platform.OS !== 'web' && <Icono nombre="micro" size={20} themeColor="textSecondary" />}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Enviar"
        accessibilityState={{ disabled: !puedeEnviar }}
        onPress={enviar}
        style={[
          styles.enviar,
          { backgroundColor: deshabilitado ? theme.backgroundSelected : theme.primary },
        ]}>
        <Icono nombre="enviar" size={20} themeColor={deshabilitado ? 'textSecondary' : 'onPrimary'} />
      </Pressable>
    </View>
  );
}

function BarraEscribir({
  margenInferior,
  children,
}: {
  margenInferior: number;
  children: React.ReactNode;
}) {
  const theme = useTheme();
  return (
    <View
      style={[
        styles.escribir,
        {
          borderTopColor: theme.hairline,
          backgroundColor: theme.background,
          marginBottom: margenInferior,
        },
      ]}>
      <View style={styles.columna}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  raiz: { flex: 1 },
  contenido: {
    paddingHorizontal: Spacing.three,
    paddingTop: Spacing.three,
    paddingBottom: Spacing.four,
    alignItems: 'center',
  },
  columna: { width: '100%', maxWidth: MaxContentWidth, gap: Spacing.three },
  columnaWeb: { width: '100%', maxWidth: Web.anchoLectura, alignSelf: 'center', gap: Spacing.four },
  campoWeb: { paddingTop: Spacing.five },
  titulo: { gap: Spacing.two, paddingBottom: Spacing.three },
  intercambio: { gap: Spacing.three },
  burbuja: {
    alignSelf: 'flex-end',
    maxWidth: 284,
    padding: Spacing.twelve,
    borderRadius: Radius.surface,
  },
  respuesta: { gap: Spacing.three },
  enlaces: { flexDirection: 'row', gap: Spacing.three },
  pista: { gap: Spacing.two, paddingTop: Spacing.five },
  subrayado: { textDecorationLine: 'underline' },
  escribir: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    alignItems: 'center',
  },
  filaEscribir: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  campo: {
    flex: 1,
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingLeft: Spacing.three,
    paddingRight: Spacing.two,
    borderRadius: Radius.pill,
  },
  entrada: { flex: 1, fontFamily: Fonts.sans, fontSize: 17, padding: 0, ...SinContornoWeb },
  enviar: {
    width: 48,
    height: 48,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
