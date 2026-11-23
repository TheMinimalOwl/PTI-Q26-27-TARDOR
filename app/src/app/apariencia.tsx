import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { CabeceraSeccion } from '@/components/cabecera-seccion';
import { GrupoAjustes } from '@/components/celda-ajuste';
import { EtiquetaSeccion } from '@/components/etiqueta-seccion';
import { Icono } from '@/components/icono';
import { PantallaDetalle } from '@/components/pantalla-detalle';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { apariencia } from '@/data/datos-ejemplo';
import { setTema, useTema } from '@/data/estado-apariencia';
import { useTheme } from '@/hooks/use-theme';

function Radio({ marcado }: { marcado: boolean }) {
  const theme = useTheme();
  const color = marcado ? theme.primary : theme.textSecondary;
  return (
    <View style={[styles.radio, { borderColor: color }]}>
      {marcado && <View style={[styles.radioPunto, { backgroundColor: color }]} />}
    </View>
  );
}

/** G3 · Apariencia. En Android, botones de radio de M3. */
export default function Apariencia() {
  const theme = useTheme();
  const tema = useTema();

  if (Platform.OS === 'android') {
    return (
      <PantallaDetalle>
        <View>
          <EtiquetaSeccion texto="Tema" />
          {apariencia.opciones.map((o) => {
            const auto = o.valor === 'auto';
            return (
              <Pressable
                key={o.valor}
                accessibilityRole="radio"
                accessibilityState={{ checked: o.valor === tema }}
                android_ripple={{ color: theme.backgroundSelected }}
                onPress={() => setTema(o.valor)}
                style={styles.opcionM3}>
                <Radio marcado={o.valor === tema} />
                <View style={styles.etiqueta}>
                  <ThemedText type="cuerpo">
                    {auto ? apariencia.m3.automatica.etiqueta : o.etiqueta}
                  </ThemedText>
                  {auto && <ThemedText type="pie">{apariencia.m3.automatica.detalle}</ThemedText>}
                </View>
              </Pressable>
            );
          })}
        </View>
        <ThemedText type="pie">{apariencia.m3.nota}</ThemedText>
      </PantallaDetalle>
    );
  }

  return (
    <PantallaDetalle>
      <View>
        <CabeceraSeccion titulo="Tema" />
        <GrupoAjustes>
          {apariencia.opciones.map((o) => (
            <Pressable
              key={o.valor}
              accessibilityRole="radio"
              accessibilityState={{ checked: o.valor === tema }}
              onPress={() => setTema(o.valor)}
              style={[styles.opcion, { borderBottomColor: theme.hairline }]}>
              <ThemedText type="cuerpo" style={styles.etiqueta}>
                {o.etiqueta}
              </ThemedText>
              {o.valor === tema && <Icono nombre="hecho" size={22} themeColor="icon" />}
            </Pressable>
          ))}
        </GrupoAjustes>
      </View>
      <ThemedText type="pie">{apariencia.nota}</ThemedText>
    </PantallaDetalle>
  );
}

const styles = StyleSheet.create({
  opcion: {
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.twelve,
    marginHorizontal: Spacing.three,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  etiqueta: { flex: 1 },
  opcionM3: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: Spacing.three },
  radio: {
    width: 20,
    height: 20,
    borderRadius: Radius.pill,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioPunto: { width: 10, height: 10, borderRadius: Radius.pill },
});
