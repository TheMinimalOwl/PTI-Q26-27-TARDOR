import { router } from 'expo-router';
import { Platform, StyleSheet, View } from 'react-native';

import { CeldaAjuste, GrupoAjustes } from '@/components/celda-ajuste';
import { ContenedorPestana } from '@/components/contenedor-pestana';
import { EtiquetaSeccion } from '@/components/etiqueta-seccion';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { apariencia, avisos, cuenta } from '@/data/datos-ejemplo';
import { useTema } from '@/data/estado-apariencia';
import { setFuenteDatos, useModoApi } from '@/data/fuente-datos';
import { useTheme } from '@/hooks/use-theme';
import { enumerar, nombreCadena } from '@/utils/formato';

const abrirAvisos = () => router.push('/avisos');
const abrirApariencia = () => router.push('/apariencia');
const cerrarSesion = () => router.replace('/bienvenida');

/** Qué usa las APIs: lo que aún no tienen (bajadas de la semana, avisos) sigue con datos de prueba. */
const notaApi =
  'Buscar, la ficha, la lista, Comparar y Ruta usan la API de precios; Preguntar, el asistente. Las bajadas de la semana y los avisos siguen con datos de prueba.';

function CeldaFuenteDatos({ enGrupo }: { enGrupo?: boolean }) {
  const modoApi = useModoApi();
  return (
    <CeldaAjuste
      enGrupo={enGrupo}
      icono="nube"
      etiqueta="Precios reales (API)"
      subtitulo={enGrupo ? undefined : modoApi ? 'Conectado a la API' : 'Datos de prueba'}
      activado={modoApi}
      onCambiar={(v) => setFuenteDatos(v ? 'api' : 'prueba')}
    />
  );
}

/** Versión Material 3: tarjeta de perfil y elementos de lista de dos líneas por secciones. */
function CuentaM3({ activos, temaActual }: { activos: number; temaActual?: string }) {
  const theme = useTheme();
  const iniciales = cuenta.nombre
    .split(' ')
    .map((p) => p[0])
    .join('');

  return (
    <>
      <View style={[styles.tarjeta, { backgroundColor: theme.backgroundElement }]}>
        <View style={[styles.avatar, { backgroundColor: theme.tint }]}>
          <ThemedText type="titular" themeColor="onTint">
            {iniciales}
          </ThemedText>
        </View>
        <View>
          <ThemedText type="titular" themeColor="text">
            {cuenta.nombre}
          </ThemedText>
          <ThemedText type="pie">{cuenta.correo}</ThemedText>
        </View>
      </View>

      <EtiquetaSeccion texto="Tu compra" />
      <CeldaAjuste icono="zona" etiqueta="Mi zona" subtitulo={cuenta.m3.zona} />
      <CeldaAjuste
        icono="tiendas"
        etiqueta="Tiendas favoritas"
        subtitulo={enumerar(cuenta.m3.tiendasFavoritas.map(nombreCadena))}
      />
      <CeldaAjuste
        icono="campana"
        etiqueta="Avisos de bajada"
        subtitulo={`${activos} activos`}
        onPress={abrirAvisos}
      />

      <EtiquetaSeccion texto="Preferencias" />
      <CeldaAjuste
        icono="luna"
        etiqueta="Apariencia"
        subtitulo={temaActual}
        onPress={abrirApariencia}
      />
      <CeldaAjuste icono="candado" etiqueta="Privacidad y datos" subtitulo={cuenta.m3.privacidad} />

      <EtiquetaSeccion texto="Datos" />
      <CeldaFuenteDatos />
      <ThemedText type="pie" style={styles.nota}>
        {notaApi}
      </ThemedText>

      <EtiquetaSeccion texto="Sesión" />
      <CeldaAjuste icono="salir" etiqueta="Cerrar sesión" subtitulo="" onPress={cerrarSesion} />
    </>
  );
}

/** G1 · Cuenta. Mi zona, Tiendas favoritas y Privacidad aún no tienen pantalla en Figma. */
export default function Cuenta() {
  const tema = useTema();
  const activos = avisos.productos.filter((a) => a.activo).length;
  const temaActual = apariencia.opciones.find((o) => o.valor === tema)?.corta;

  if (Platform.OS === 'android') {
    return (
      <ContenedorPestana titulo="Cuenta">
        <CuentaM3 activos={activos} temaActual={temaActual} />
      </ContenedorPestana>
    );
  }

  return (
    <ContenedorPestana titulo="Cuenta">
      <View style={styles.perfil}>
        <ThemedText type="titular" themeColor="text">
          {cuenta.nombre}
        </ThemedText>
        <ThemedText type="pie">{cuenta.correo}</ThemedText>
      </View>

      <View style={styles.grupos}>
        <GrupoAjustes>
          <CeldaAjuste enGrupo icono="zona" etiqueta="Mi zona" detalle={cuenta.zona} />
          <CeldaAjuste
            enGrupo
            icono="tiendas"
            etiqueta="Tiendas favoritas"
            detalle={String(cuenta.tiendasFavoritas)}
          />
          <CeldaAjuste
            enGrupo
            icono="campana"
            etiqueta="Avisos de bajada"
            detalle={`${activos} activos`}
            onPress={abrirAvisos}
          />
        </GrupoAjustes>

        <GrupoAjustes>
          <CeldaAjuste
            enGrupo
            icono="luna"
            etiqueta="Apariencia"
            detalle={temaActual}
            onPress={abrirApariencia}
          />
          <CeldaAjuste enGrupo icono="candado" etiqueta="Privacidad y datos" />
        </GrupoAjustes>

        <View style={styles.conNota}>
          <GrupoAjustes>
            <CeldaFuenteDatos enGrupo />
          </GrupoAjustes>
          <ThemedText type="pie" style={styles.notaGrupo}>
            {notaApi}
          </ThemedText>
        </View>

        <GrupoAjustes>
          <CeldaAjuste enGrupo icono="salir" etiqueta="Cerrar sesión" onPress={cerrarSesion} />
        </GrupoAjustes>
      </View>

      <ThemedText type="nota" style={styles.pie}>
        {cuenta.pie}
      </ThemedText>
    </ContenedorPestana>
  );
}

const styles = StyleSheet.create({
  perfil: { gap: 2, paddingTop: Spacing.two, paddingBottom: Spacing.four },
  grupos: { gap: Spacing.four },
  pie: { paddingTop: Spacing.two },
  nota: { paddingTop: Spacing.one },
  conNota: { gap: Spacing.two },
  notaGrupo: { paddingHorizontal: Spacing.three },
  tarjeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.three,
    marginTop: Spacing.three,
    borderRadius: Radius.surface,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
