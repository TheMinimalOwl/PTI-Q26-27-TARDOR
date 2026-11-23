import { useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { VistaPreguntar } from '@/components/vista-preguntar';
import { PaginaWeb } from '@/components/web/pagina-web';
import { Web } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useAltoMenuWeb, useEscritorio } from '@/hooks/use-web';

/**
 * D1 · Preguntar (W5 en la web ancha), con D2 sin conexión: `?sinConexion=1`.
 * Se abre desde Inicio y el menú web; en Buscar del móvil va en el control segmentado.
 */
export default function Preguntar() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const altoMenuWeb = useAltoMenuWeb();
  const escritorio = useEscritorio();
  const { sinConexion } = useLocalSearchParams<{ sinConexion?: string }>();

  if (escritorio) {
    return (
      <PaginaWeb ancho={Web.anchoLectura}>
        <VistaPreguntar escritorio sinConexion={sinConexion === '1'} />
      </PaginaWeb>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: theme.background, paddingTop: altoMenuWeb }}>
      <VistaPreguntar sinConexion={sinConexion === '1'} margenInferior={insets.bottom} />
    </View>
  );
}
