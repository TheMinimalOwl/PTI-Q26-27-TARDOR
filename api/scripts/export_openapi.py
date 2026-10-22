"""Exporta el contracte OpenAPI a api/openapi.json (no necessita BD ni Redis).

Executar des d'api/:  python scripts/export_openapi.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

(ROOT / "openapi.json").write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("openapi.json actualizado")
