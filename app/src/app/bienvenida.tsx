import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Boton } from '@/components/boton';
import { PantallaDetalle } from '@/components/pantalla-detalle';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { app } from '@/data/datos-ejemplo';

/** A1 · Bienvenida */
export default function Bienvenida() {
  return (
    <PantallaDetalle sinCabecera llenar estiloContenido={styles.contenido}>
      <View style={styles.texto}>
        <ThemedText type="display">{app.nombre}</ThemedText>
        <ThemedText type="cuerpo">{app.frase}</ThemedText>
      </View>

      <View style={styles.espacio} />

      <View style={styles.acciones}>
        <Boton etiqueta="Crear cuenta" onPress={() => router.push('/crear-cuenta')} />
        <Boton
          tipo="texto"
          etiqueta="Ya tengo cuenta"
          onPress={() => router.push('/crear-cuenta')}
        />
        <Boton
          tipo="textoNeutro"
          etiqueta="Probar sin cuenta"
          onPress={() => router.replace('/screens/inicio')}
        />
      </View>
    </PantallaDetalle>
  );
}

const styles = StyleSheet.create({
  contenido: { paddingTop: 96, paddingHorizontal: Spacing.two },
  texto: { gap: Spacing.three },
  espacio: { flex: 1 },
  acciones: { gap: Spacing.two, paddingBottom: Spacing.two },
});
