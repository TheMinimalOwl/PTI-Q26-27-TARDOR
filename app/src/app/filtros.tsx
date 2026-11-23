import { router } from 'expo-router';
import { useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Boton } from '@/components/boton';
import { Icono } from '@/components/icono';
import { OpcionSeleccionable } from '@/components/opcion-seleccionable';
import { ThemedText } from '@/components/themed-text';
import { Cadenas, Spacing, type CadenaId } from '@/constants/theme';
import { filtros } from '@/data/datos-ejemplo';
import { filtrosVacios, setFiltros, useFiltros } from '@/data/estado-filtros';
import { useTheme } from '@/hooks/use-theme';
import { useAltoMenuWeb } from '@/hooks/use-web';

/** B3 · Filtros (hoja modal nativa). Se aplican al pulsar el botón. */
export default function Filtros() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const altoMenuWeb = useAltoMenuWeb();
  const actuales = useFiltros();
  const [orden, setOrden] = useState(actuales.orden);
  const [cadenas, setCadenas] = useState<CadenaId[]>(actuales.cadenas);

  const alternarCadena = (id: CadenaId) =>
    setCadenas((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  const aplicar = () => {
    setFiltros({ orden, cadenas });
    router.back();
  };

  return (
    <View style={[styles.raiz, { backgroundColor: theme.surface }]}>
      <View
        style={[
          styles.cabecera,
          // En Android el modal ocupa toda la pantalla y va bajo la barra de estado.
          Platform.OS === 'android' && { paddingTop: insets.top + Spacing.two },
          Platform.OS === 'web' && { paddingTop: altoMenuWeb + Spacing.two },
        ]}>
        <Pressable
          accessibilityRole="button"
          hitSlop={8}
          onPress={() => {
            setOrden(filtrosVacios.orden);
            setCadenas(filtrosVacios.cadenas);
          }}
          style={styles.lado}>
          <ThemedText type="cuerpo" themeColor="link">
            Borrar
          </ThemedText>
        </Pressable>
        <ThemedText type="titular" style={styles.titulo}>
          Filtros
        </ThemedText>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Cerrar"
          onPress={() => router.back()}
          style={[styles.lado, styles.cerrar]}>
          <Icono nombre="cerrar" />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.opciones}>
        <ThemedText type="etiqueta" style={styles.seccion}>
          Ordenar por
        </ThemedText>
        {filtros.ordenes.map((o) => (
          <OpcionSeleccionable
            key={o}
            etiqueta={o}
            marcada={o === orden}
            onPress={() => setOrden(o)}
          />
        ))}

        <ThemedText type="etiqueta" style={styles.seccion}>
          Cadenas
        </ThemedText>
        {Cadenas.map((c) => (
          <OpcionSeleccionable
            key={c.id}
            etiqueta={c.nombre}
            marcada={cadenas.includes(c.id)}
            onPress={() => alternarCadena(c.id)}
          />
        ))}
      </ScrollView>

      <View style={[styles.pie, { paddingBottom: insets.bottom + Spacing.two }]}>
        <Boton
          etiqueta={cadenas.length === 0 ? 'Marca al menos una cadena' : 'Ver resultados'}
          deshabilitado={cadenas.length === 0}
          onPress={aplicar}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  raiz: { flex: 1 },
  cabecera: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: Spacing.three,
    paddingRight: Spacing.two,
    paddingTop: Spacing.four,
  },
  lado: { width: 80, height: 44, justifyContent: 'center' },
  cerrar: { alignItems: 'flex-end' },
  titulo: { flex: 1, textAlign: 'center' },
  opciones: { paddingHorizontal: Spacing.three, paddingBottom: Spacing.three },
  seccion: { paddingTop: Spacing.three, paddingBottom: Spacing.one },
  pie: { paddingHorizontal: Spacing.three, paddingTop: Spacing.two },
});
