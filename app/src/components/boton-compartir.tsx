import { Pressable, Share, StyleSheet } from 'react-native';

import { Icono } from '@/components/icono';

/** Acción de la barra superior: hoja de compartir nativa del sistema. */
export function BotonCompartir({ mensaje }: { mensaje: string }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Compartir"
      hitSlop={8}
      onPress={() => Share.share({ message: mensaje })}
      style={styles.boton}>
      <Icono nombre="compartir" size={22} themeColor="link" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  boton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
});
