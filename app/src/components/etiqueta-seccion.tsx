import { StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

/** Título de grupo de una lista M3 (Android). */
export function EtiquetaSeccion({ texto }: { texto: string }) {
  return (
    <ThemedText type="pieMedio" themeColor="textSecondary" style={styles.etiqueta}>
      {texto}
    </ThemedText>
  );
}

const styles = StyleSheet.create({
  etiqueta: { paddingTop: Spacing.three, paddingBottom: Spacing.one },
});
