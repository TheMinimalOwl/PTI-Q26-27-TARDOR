"""Prova d'integració ingesta → API: publica a NATS fitxers `clean` del normalitzador,
amb el mateix sobre que flujo-entrada/fission/normalizer/consumer.py, perquè els
reculli l'api-writer.

La cadena surt del nom del fitxer (`mercadona_clean.txt` → scraper.mercadona.clean).

Executar des de l'arrel del repo, amb NATS, la BD i el writer en marxa:
    api\\.venv\\Scripts\\python api\\scripts\\prova_integracio.py flujo-ia\\data\\raw\\mercadona_clean.txt
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import nats


async def main(files: list[str]) -> None:
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    for f in files:
        path = Path(f)
        chain = path.name.split("_")[0]
        txt = path.read_text(encoding="utf-8")
        out = {
            "source": "normalizer",
            "wh": "default",
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "clean": txt,
        }
        await js.publish(f"scraper.{chain}.clean", json.dumps(out, ensure_ascii=False).encode())
        print(f"{chain}: enviat a scraper.{chain}.clean")
    await nc.close()


asyncio.run(main(sys.argv[1:]))
