import { Slot } from 'expo-router';

/**
 * En la web no hay barra de pestañas: las secciones están en el menú superior (MenuWeb), que
 * vive en el layout raíz para que también se vea en la ficha, Comparar y Preguntar.
 */
export default function AppTabs() {
  return <Slot />;
}
