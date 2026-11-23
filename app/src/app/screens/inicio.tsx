import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { CabeceraSeccion } from '@/components/cabecera-seccion';
import { CampoBusqueda } from '@/components/campo-busqueda';
import { ContenedorPestana } from '@/components/contenedor-pestana';
import { FilaCatalogo } from '@/components/fila-producto';
import { Icono } from '@/components/icono';
import { ResumenLista } from '@/components/resumen-lista';
import { ThemedText } from '@/components/themed-text';
import { InicioWeb } from '@/components/web/inicio-web';
import { Spacing } from '@/constants/theme';
import { bajadasSemana, inicio } from '@/data/datos-ejemplo';
import { useTheme } from '@/hooks/use-theme';
import { useEscritorio } from '@/hooks/use-web';

const abrirBusqueda = () => router.push('/screens/buscar');

/** B1 · Inicio (W1 en la web ancha) */
export default function Inicio() {
  return useEscritorio() ? <InicioWeb /> : <InicioMovil />;
}

function InicioMovil() {
  const theme = useTheme();
  const [umbralBuscador, setUmbralBuscador] = useState(0);

  return (
    <ContenedorPestana
      titulo={inicio.titulo}
      subtitulo={inicio.actualizado}
      accion={{
        icono: 'campana',
        etiqueta: 'Avisos de bajada',
        onPress: () => router.push('/avisos'),
      }}
      fijo={<CampoBusqueda onPress={abrirBusqueda} />}
      umbralFijo={umbralBuscador}>
      <View style={styles.aire} />

      <View onLayout={(e) => setUmbralBuscador(e.nativeEvent.layout.y)}>
        <CampoBusqueda onPress={abrirBusqueda} />
      </View>

      <Pressable
        accessibilityRole="link"
        onPress={() => router.push('/preguntar')}
        style={[styles.preguntar, { borderBottomColor: theme.hairline }]}>
        <Icono nombre="preguntar" size={20} themeColor="textSecondary" />
        <ThemedText type="pie" style={styles.espacio}>
          {`Preguntar: «${inicio.preguntaSugerida}»`}
        </ThemedText>
        <Icono nombre="siguiente" size={20} themeColor="textSecondary" />
      </Pressable>

      <ResumenLista />

      {/* La API aún no calcula bajadas: esta sección sale siempre de los datos de prueba. */}
      <CabeceraSeccion
        titulo="Han bajado esta semana"
        enlace="Ver todo"
        onPressEnlace={abrirBusqueda}
      />
      {bajadasSemana.map((producto) => (
        <FilaCatalogo key={producto.id} producto={producto} />
      ))}
    </ContenedorPestana>
  );
}

const styles = StyleSheet.create({
  aire: { height: Spacing.three },
  espacio: { flex: 1 },
  preguntar: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    paddingVertical: Spacing.twelve,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
});
