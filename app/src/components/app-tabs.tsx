import { NativeTabs } from 'expo-router/native-tabs';

import { Fonts } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** Las 4 pestañas del diseño: Inicio, Buscar, Lista y Cuenta. La ruta se abre desde Lista. */
export default function AppTabs() {
  const colors = useTheme();
  // Sin esto la pestaña nueva se ve en blanco un instante antes de pintarse.
  const fondo = { backgroundColor: colors.background };

  return (
    <NativeTabs
      backgroundColor={colors.background}
      indicatorColor={colors.backgroundSelected}
      iconColor={{ default: colors.textSecondary, selected: colors.link }}
      labelStyle={{
        default: { color: colors.textSecondary, fontFamily: Fonts.sansMedium },
        selected: { color: colors.link, fontFamily: Fonts.sansMedium },
      }}>
      <NativeTabs.Trigger name="inicio" contentStyle={fondo}>
        <NativeTabs.Trigger.Label>Inicio</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'house', selected: 'house.fill' }} md="home" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="buscar" contentStyle={fondo}>
        <NativeTabs.Trigger.Label>Buscar</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="magnifyingglass" md="search" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="lista" contentStyle={fondo}>
        <NativeTabs.Trigger.Label>Lista</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="checklist" md="checklist" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="cuenta" contentStyle={fondo}>
        <NativeTabs.Trigger.Label>Cuenta</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'person', selected: 'person.fill' }} md="person" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
