const meses = [
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
];

/** «2026-10-20» → «20 oct 2026» (o «oct 2026» sin día). */
export function fechaCorta(iso: string, conDia = true) {
  const [anio, mes, dia] = iso.split('-').map(Number);
  const texto = `${meses[mes - 1]} ${anio}`;
  return conDia ? `${dia} ${texto}` : texto;
}

/** Fecha ISO de hace `n` meses respecto a `hasta` (YYYY-MM-DD). */
export function haceMeses(hasta: string, n: number) {
  const [anio, mes, dia] = hasta.split('-').map(Number);
  return new Date(Date.UTC(anio, mes - 1 - n, dia)).toISOString().slice(0, 10);
}
