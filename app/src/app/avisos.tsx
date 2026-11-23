import { useState } from 'react';
import { Linking, Platform, StyleSheet, View } from 'react-native';

import { Aviso } from '@/components/aviso';
import { Boton } from '@/components/boton';
import { CabeceraSeccion } from '@/components/cabecera-seccion';
import { CeldaAjuste, GrupoAjustes } from '@/components/celda-ajuste';
import { EtiquetaSeccion } from '@/components/etiqueta-seccion';
import { Icono } from '@/components/icono';
import { PantallaDetalle } from '@/components/pantalla-detalle';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { avisos } from '@/data/datos-ejemplo';
import { formatoPrecio } from '@/utils/formato';
import { useTheme } from '@/hooks/use-theme';

const abrirAjustes = () => Linking.openSettings();

/** G2 · Avisos de bajada */
export default function Avisos() {
  const theme = useTheme();
  const m3 = Platform.OS === 'android';
  const [activos, setActivos] = useState(
    Object.fromEntries(avisos.productos.map((a) => [a.id, a.activo])) as Record<string, boolean>,
  );
  const [resumenLunes, setResumenLunes] = useState(avisos.resumenLunes);
  const alternar = (id: string) => (v: boolean) => setActivos((x) => ({ ...x, [id]: v }));

  if (m3) {
    return (
      <PantallaDetalle>
        <View style={[styles.avisoM3, { backgroundColor: theme.tint }]}>
          <View style={styles.cabeceraAviso}>
            <Icono nombre="alerta" size={20} themeColor="onTint" />
            <ThemedText type="cuerpo15Medio" themeColor="onTint" style={styles.espacio}>
              {avisos.notificaciones.titulo}
            </ThemedText>
          </View>
          <ThemedText type="pie" themeColor="onTint">
            {avisos.notificaciones.textoM3}
          </ThemedText>
          <Boton etiqueta="Abrir ajustes" onPress={abrirAjustes} style={styles.abrir} />
        </View>

        <View>
          <EtiquetaSeccion texto="Avisar cuando baje de" />
          {avisos.productos.map((a) => (
            <CeldaAjuste
              key={a.id}
              icono="campana"
              etiqueta={a.nombreM3}
              subtitulo={`Por debajo de ${formatoPrecio(a.bajoDe)}`}
              activado={activos[a.id]}
              onCambiar={alternar(a.id)}
            />
          ))}

          <EtiquetaSeccion texto="Resumen" />
          <CeldaAjuste
            icono="reloj"
            etiqueta={avisos.resumenM3.titulo}
            subtitulo={avisos.resumenM3.detalle}
            activado={resumenLunes}
            onCambiar={setResumenLunes}
          />
        </View>
      </PantallaDetalle>
    );
  }

  return (
    <PantallaDetalle>
      <Aviso
        icono="info"
        titulo={avisos.notificaciones.titulo}
        texto={avisos.notificaciones.texto}
        accion={{ etiqueta: 'Activar', onPress: abrirAjustes }}
      />

      <View>
        <CabeceraSeccion titulo="Avisar cuando baje de" />
        <GrupoAjustes>
          {avisos.productos.map((a) => (
            <CeldaAjuste
              key={a.id}
              enGrupo
              icono="campana"
              etiqueta={`${a.nombre}, ${formatoPrecio(a.bajoDe)}`}
              activado={activos[a.id]}
              onCambiar={alternar(a.id)}
            />
          ))}
        </GrupoAjustes>
      </View>

      <GrupoAjustes>
        <CeldaAjuste
          enGrupo
          icono="reloj"
          etiqueta="Resumen de bajadas los lunes"
          activado={resumenLunes}
          onCambiar={setResumenLunes}
        />
      </GrupoAjustes>
    </PantallaDetalle>
  );
}

const styles = StyleSheet.create({
  espacio: { flex: 1 },
  avisoM3: { gap: Spacing.two, padding: Spacing.three, borderRadius: Radius.surface },
  cabeceraAviso: { flexDirection: 'row', alignItems: 'center', gap: Spacing.twelve },
  abrir: { alignSelf: 'flex-end', marginTop: Spacing.one },
});
