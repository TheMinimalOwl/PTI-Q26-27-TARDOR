import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { colorMarca, Spacing, type SlugCadena } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useTheme } from '@/hooks/use-theme';
import { nombreCadena } from '@/utils/formato';

type Props = {
  id: SlugCadena;
  secundario?: boolean;
  /** Pie/13 Medio y nombre corto (la primera palabra), como en las cabeceras de columna de la web. */
  pequena?: boolean;
};

/** Nombre neutro con un punto de 8 px en el color de marca: el color nunca va en el texto. */
export function Cadena({ id, secundario, pequena }: Props) {
  const theme = useTheme();
  const color = colorMarca(id, useColorScheme()) ?? theme.textSecondary;

  return (
    <View style={styles.fila}>
      <View style={[styles.punto, { backgroundColor: color }]} />
      <ThemedText
        type={pequena ? 'pieMedio' : 'cuerpo15Medio'}
        themeColor={secundario || pequena ? 'textSecondary' : 'text'}
        numberOfLines={1}>
        {pequena ? nombreCadena(id).split(' ')[0] : nombreCadena(id)}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  punto: { width: 8, height: 8, borderRadius: Spacing.one },
});
