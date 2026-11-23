import { router, usePathname, type Href } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { CampoBusqueda } from '@/components/campo-busqueda';
import { Icono, type NombreIcono } from '@/components/icono';
import { ThemedText } from '@/components/themed-text';
import { MaxContentWidth, Spacing, Web } from '@/constants/theme';
import { setTema } from '@/data/estado-apariencia';
import { useLista } from '@/data/estado-lista';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useTheme } from '@/hooks/use-theme';
import { useEscritorio } from '@/hooks/use-web';

type Seccion = { etiqueta: string; href: Href; ruta: string };

const abrirBuscar = () => router.push('/screens/buscar');

/** Navegación web (Figma «Navegación web»): la sección activa en peso medio y color principal. */
export function MenuWeb() {
  const theme = useTheme();
  const escritorio = useEscritorio();
  const pathname = usePathname();
  const oscuro = useColorScheme() === 'dark';
  const productos = useLista().length;
  const [menuAbierto, setMenuAbierto] = useState(false);

  const secciones: Seccion[] = [
    { etiqueta: 'Inicio', href: '/screens/inicio', ruta: '/screens/inicio' },
    { etiqueta: 'Buscar', href: '/screens/buscar', ruta: '/screens/buscar' },
    {
      etiqueta: productos ? `Mi lista · ${productos}` : 'Mi lista',
      href: '/screens/lista',
      ruta: '/screens/lista',
    },
    { etiqueta: 'Preguntar', href: '/preguntar', ruta: '/preguntar' },
  ];
  const cuenta: Seccion = { etiqueta: 'Cuenta', href: '/screens/cuenta', ruta: '/screens/cuenta' };

  // La ficha de producto cuelga de Buscar; Comparar y Ruta, de la lista.
  const activa = (s: Seccion) =>
    pathname.startsWith(s.ruta) ||
    (s.ruta === '/screens/buscar' && pathname.startsWith('/producto')) ||
    (s.ruta === '/screens/lista' && (pathname === '/comparar' || pathname === '/ruta'));

  const tema = (
    <BotonIcono
      icono={oscuro ? 'sol' : 'luna'}
      etiqueta={oscuro ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
      onPress={() => setTema(oscuro ? 'light' : 'dark')}
    />
  );

  return (
    <View
      style={[
        styles.barra,
        {
          height: escritorio ? Web.altoMenu : Web.altoMenuEstrecho,
          backgroundColor: theme.surface,
          borderBottomColor: theme.hairline,
        },
        !escritorio && styles.barraEstrecha,
      ]}>
      <View style={[styles.contenido, { gap: escritorio ? Spacing.five : Spacing.one }]}>
        <Pressable
          accessibilityRole="link"
          accessibilityLabel="SuperAhorro, inicio"
          onPress={() => router.push('/screens/inicio')}>
          <ThemedText type="titulo">SuperAhorro</ThemedText>
        </Pressable>

        {escritorio ? (
          <>
            <View style={styles.enlaces}>
              {secciones.map((s) => (
                <Pressable key={s.ruta} accessibilityRole="link" onPress={() => router.push(s.href)}>
                  <ThemedText
                    type={activa(s) ? 'cuerpo15Medio' : 'cuerpo15'}
                    themeColor={activa(s) ? 'text' : 'textSecondary'}>
                    {s.etiqueta}
                  </ThemedText>
                </Pressable>
              ))}
            </View>
            <View style={styles.espacio} />
            {pathname !== '/screens/inicio' && (
              <View style={styles.buscador}>
                <CampoBusqueda onPress={abrirBuscar} />
              </View>
            )}
            {tema}
            <BotonIcono icono="cuenta" etiqueta="Cuenta" onPress={() => router.push(cuenta.href)} />
          </>
        ) : (
          <>
            <View style={styles.espacio} />
            <BotonIcono icono="buscar" etiqueta="Buscar" onPress={abrirBuscar} />
            <BotonIcono
              icono="lista"
              etiqueta="Mi lista"
              onPress={() => router.push('/screens/lista')}
            />
            {tema}
            <BotonIcono
              icono={menuAbierto ? 'cerrar' : 'menu'}
              etiqueta="Menú"
              onPress={() => setMenuAbierto((a) => !a)}
            />
          </>
        )}
      </View>

      {!escritorio && menuAbierto && (
        <View
          style={[
            styles.desplegable,
            { backgroundColor: theme.surface, borderBottomColor: theme.hairline },
          ]}>
          {[...secciones, cuenta].map((s) => (
            <Pressable
              key={s.ruta}
              accessibilityRole="link"
              onPress={() => {
                setMenuAbierto(false);
                router.push(s.href);
              }}
              style={[styles.opcion, { borderBottomColor: theme.hairline }]}>
              <ThemedText
                type={activa(s) ? 'cuerpo15Medio' : 'cuerpo15'}
                themeColor={activa(s) ? 'text' : 'textSecondary'}>
                {s.etiqueta}
              </ThemedText>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

function BotonIcono({
  icono,
  etiqueta,
  onPress,
}: {
  icono: NombreIcono;
  etiqueta: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={etiqueta}
      onPress={onPress}
      style={styles.icono}>
      <Icono nombre={icono} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  barra: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingHorizontal: Spacing.five,
    justifyContent: 'center',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  barraEstrecha: { paddingHorizontal: Spacing.three },
  contenido: {
    width: '100%',
    maxWidth: MaxContentWidth,
    flexDirection: 'row',
    alignItems: 'center',
  },
  enlaces: { flexDirection: 'row', alignItems: 'center', gap: Spacing.four },
  espacio: { flex: 1 },
  buscador: { width: 320 },
  icono: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  desplegable: {
    position: 'absolute',
    top: Web.altoMenuEstrecho,
    left: 0,
    right: 0,
    paddingHorizontal: Spacing.three,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  opcion: { minHeight: 48, justifyContent: 'center', borderBottomWidth: StyleSheet.hairlineWidth },
});
