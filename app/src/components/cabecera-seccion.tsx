import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

type Props = { titulo: string; enlace?: string; onPressEnlace?: () => void };

export function CabeceraSeccion({ titulo, enlace, onPressEnlace }: Props) {
  return (
    <View style={styles.fila}>
      <ThemedText type="titular" themeColor="title">
        {titulo}
      </ThemedText>
      {enlace && (
        <Pressable accessibilityRole="link" hitSlop={12} onPress={onPressEnlace}>
          <ThemedText type="pieMedio" themeColor="link">
            {enlace}
          </ThemedText>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fila: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingTop: Spacing.four,
    paddingBottom: Spacing.two,
  },
});
