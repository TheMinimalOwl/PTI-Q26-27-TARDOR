import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Boton } from '@/components/boton';
import { CampoTexto } from '@/components/campo-texto';
import { PantallaDetalle } from '@/components/pantalla-detalle';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { cuenta } from '@/data/datos-ejemplo';
import { useTheme } from '@/hooks/use-theme';

const entrar = () => router.replace('/screens/inicio');

/** A2 · Crear cuenta */
export default function CrearCuenta() {
  const theme = useTheme();
  const [correo, setCorreo] = useState(cuenta.correo);
  const [contrasena, setContrasena] = useState('');

  return (
    <PantallaDetalle llenar>
      <ThemedText type="titulo">Crear cuenta</ThemedText>
      <ThemedText type="cuerpo15" themeColor="textSecondary">
        Guarda tu lista y recibe avisos cuando baje un producto.
      </ThemedText>

      <CampoTexto
        etiqueta="Correo electrónico"
        value={correo}
        onChangeText={setCorreo}
        keyboardType="email-address"
        autoCapitalize="none"
        autoComplete="email"
      />
      <CampoTexto
        etiqueta="Contraseña"
        contrasena
        value={contrasena}
        onChangeText={setContrasena}
        placeholder="Mínimo 8 caracteres"
        autoComplete="new-password"
      />

      <Boton etiqueta="Crear cuenta" onPress={entrar} />

      <View style={styles.separador}>
        <View style={[styles.linea, { backgroundColor: theme.hairline }]} />
        <ThemedText type="pie">o</ThemedText>
        <View style={[styles.linea, { backgroundColor: theme.hairline }]} />
      </View>

      <Boton tipo="secundario" etiqueta="Continuar con Apple" onPress={entrar} />
      <Boton tipo="secundario" etiqueta="Continuar con Google" onPress={entrar} />

      <View style={styles.espacio} />

      <ThemedText type="pie" style={styles.legal}>
        Al crear la cuenta aceptas las{' '}
        <ThemedText type="pie" themeColor="link" style={styles.subrayado}>
          condiciones de uso
        </ThemedText>{' '}
        y la{' '}
        <ThemedText type="pie" themeColor="link" style={styles.subrayado}>
          política de privacidad
        </ThemedText>
        .
      </ThemedText>
    </PantallaDetalle>
  );
}

const styles = StyleSheet.create({
  separador: { flexDirection: 'row', alignItems: 'center', gap: Spacing.twelve },
  linea: { flex: 1, height: 1 },
  espacio: { flex: 1 },
  legal: { textAlign: 'center' },
  subrayado: { textDecorationLine: 'underline' },
});
