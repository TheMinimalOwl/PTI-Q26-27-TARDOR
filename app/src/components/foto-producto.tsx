import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Fonts } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = { formato: string; tamano: 48 | 64 | 96 | 384 };

/** Hueco 1:1 de la foto (Figma «Foto de producto»): mientras no hay fotos, el formato en serif. */
export function FotoProducto({ formato, tamano }: Props) {
  const theme = useTheme();
  const largo = formato.length > 4;
  const texto =
    tamano === 384
      ? { fontSize: 56, lineHeight: 64 }
      : tamano === 96
        ? { fontSize: 26, lineHeight: 32 }
        : tamano === 64
          ? { fontSize: largo ? 16 : 18, lineHeight: 22 }
          : { fontSize: largo ? 12 : 14, lineHeight: 18 };
  const margen = tamano === 384 ? 28 : tamano === 96 ? 10 : 5;

  return (
    <View
      style={[
        styles.foto,
        {
          width: tamano,
          height: tamano,
          padding: margen,
          paddingBottom: margen - 1,
          backgroundColor: theme.backgroundSelected,
        },
      ]}>
      <ThemedText numberOfLines={1} style={[styles.formato, texto, { color: theme.title }]}>
        {formato}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  foto: { borderRadius: 8, justifyContent: 'flex-end', overflow: 'hidden' },
  formato: { fontFamily: Fonts.serif },
});
