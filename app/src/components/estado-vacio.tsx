import { StyleSheet, View } from 'react-native';

import { Boton } from '@/components/boton';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

type Props = {
  titulo: string;
  texto: string;
  accion?: { etiqueta: string; onPress: () => void; principal?: boolean };
};

/** Vacíos y errores: alineados a la izquierda, sin icono grande. */
export function EstadoVacio({ titulo, texto, accion }: Props) {
  return (
    <View style={styles.estado}>
      <ThemedText type="titulo" themeColor="text">
        {titulo}
      </ThemedText>
      <ThemedText type="cuerpo15" themeColor="textSecondary">
        {texto}
      </ThemedText>
      {accion && (
        <Boton
          tipo={accion.principal ? 'primario' : 'secundario'}
          etiqueta={accion.etiqueta}
          onPress={accion.onPress}
          style={styles.boton}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  estado: { gap: Spacing.two, paddingTop: 40 },
  boton: { alignSelf: 'flex-start', marginTop: Spacing.two },
});
