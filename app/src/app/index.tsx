import { Redirect } from 'expo-router';

/** La app abre en la pestaña Inicio. */
export default function Index() {
  return <Redirect href="/screens/inicio" />;
}
