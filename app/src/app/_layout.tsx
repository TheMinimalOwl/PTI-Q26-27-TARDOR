import { DarkTheme, DefaultTheme, Stack, ThemeProvider, usePathname } from 'expo-router';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import * as SystemUI from 'expo-system-ui';
import { useEffect, useRef } from 'react';
import { Platform, View } from 'react-native';

import { MenuWeb } from '@/components/web/menu-web';
import { Colors, Fonts } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { hapticaCambio } from '@/utils/haptica';

SplashScreen.preventAutoHideAsync();

const web = Platform.OS === 'web';

export default function RootLayout() {
  const scheme = useColorScheme();
  const colors = Colors[scheme];
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;

  const [fontsLoaded, fontError] = useFonts({
    [Fonts.serif]: require('@/assets/fonts/SourceSerif4_500Medium.ttf'),
    [Fonts.sans]: require('@/assets/fonts/SourceSans3_400Regular.ttf'),
    [Fonts.sansMedium]: require('@/assets/fonts/SourceSans3_500Medium.ttf'),
    [Fonts.sansSemiBold]: require('@/assets/fonts/SourceSans3_600SemiBold.ttf'),
  });

  // Toque al cambiar de pantalla (pestañas, enlaces y gesto de atrás), salvo en la primera carga.
  const pathname = usePathname();
  const primeraRuta = useRef(true);
  useEffect(() => {
    if (primeraRuta.current) {
      primeraRuta.current = false;
      return;
    }
    hapticaCambio();
  }, [pathname]);

  // Fondo de la vista raíz nativa: evita destellos blancos entre pantallas en modo oscuro.
  useEffect(() => {
    SystemUI.setBackgroundColorAsync(colors.background);
  }, [colors.background]);

  useEffect(() => {
    if (fontsLoaded || fontError) {
      SplashScreen.hideAsync();
    }
  }, [fontsLoaded, fontError]);

  if (!fontsLoaded && !fontError) {
    return null;
  }

  const navigationTheme = {
    ...base,
    colors: {
      ...base.colors,
      primary: colors.link,
      background: colors.background,
      card: colors.background,
      text: colors.text,
      border: colors.hairline,
      notification: colors.up,
    },
  };

  return (
    <ThemeProvider value={navigationTheme}>
      <View style={{ flex: 1, backgroundColor: colors.background }}>
        <Stack
          screenOptions={{
            // En la web manda el menú superior (MenuWeb): sin barra de navegación por pantalla.
            headerShown: !web,
            headerTintColor: colors.link,
            // M3: barra superior con el título en serif 22
            headerTitleStyle: Platform.select({
              android: { fontFamily: Fonts.serif, fontSize: 22, color: colors.title },
              default: { fontFamily: Fonts.sansSemiBold, color: colors.text },
            }),
            headerStyle: { backgroundColor: colors.background },
            headerShadowVisible: false,
            contentStyle: { backgroundColor: colors.background },
          }}>
          <Stack.Screen name="screens" options={{ headerShown: false, title: 'Inicio' }} />
          <Stack.Screen name="index" options={{ headerShown: false }} />

          {/* A · Acceso */}
          <Stack.Screen name="bienvenida" options={{ headerShown: false }} />
          <Stack.Screen name="crear-cuenta" options={{ title: '', headerBackTitle: 'Atrás' }} />

          {/* B · Búsqueda */}
          <Stack.Screen name="filtros" options={{ headerShown: false, presentation: 'modal' }} />

          {/* C · Producto */}
          <Stack.Screen name="producto/[id]/index" options={{ title: '' }} />
          <Stack.Screen
            name="producto/[id]/evolucion"
            options={{ title: 'Evolución del precio' }}
          />

          {/* D · Preguntar */}
          <Stack.Screen name="preguntar" options={{ title: 'Preguntar' }} />

          {/* E y F · Lista, cesta y ruta */}
          <Stack.Screen name="comparar" options={{ title: 'Comparar cesta' }} />
          <Stack.Screen name="ruta" options={{ headerShown: false }} />

          {/* G · Cuenta */}
          <Stack.Screen name="avisos" options={{ title: 'Avisos de bajada' }} />
          <Stack.Screen name="apariencia" options={{ title: 'Apariencia' }} />
        </Stack>
        {web && <MenuWeb />}
      </View>
    </ThemeProvider>
  );
}
