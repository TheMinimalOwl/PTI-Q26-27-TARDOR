"""Resume los lotes `clean` que llegan por stdin (salida de `nats sub --raw`, un JSON por línea).

Imprime "lotes productos errores incompletos":
- errores: líneas `ERROR id=...` (productos que no validan en el normalizador).
- incompletos: líneas sin precio por unidad (`| - (motivo)`), que no son error.

Lo usa e2e.sh para comprobar los lotes de una pasada.
"""
import json
import sys

lotes = productos = errores = incompletos = 0
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("{"):
        continue
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    lotes += 1
    productos += int(msg.get("batch", 0))
    for l in msg.get("clean", "").splitlines():
        if l.startswith("ERROR"):
            errores += 1
        elif " | - (" in l:
            incompletos += 1
print(lotes, productos, errores, incompletos)
