"""Genera docs/index.html da site/template.html e site/data.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "site" / "data.json").read_text(encoding="utf-8"))
problemi = json.loads((ROOT / "dati" / "problemi_inseriti.json").read_text(encoding="utf-8"))
html = (ROOT / "site" / "template.html").read_text(encoding="utf-8")
html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__N_INSERITI__", str(len(problemi)))
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(html, encoding="utf-8")
print("docs/index.html", len(html))
