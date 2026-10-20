"""Печатает замечания BSL Language Server из JSON-отчета; код возврата 1, если они есть.

python scripts/bsl-check.py <каталог с отчетом>
"""

import json
import sys
from pathlib import Path
from urllib.parse import unquote

report = next(Path(sys.argv[1]).glob("*.json"))
data = json.loads(report.read_text(encoding="utf-8"))

count = 0
for file in data["fileinfos"]:
    path = unquote(file["path"]).split("/src/", 1)[-1]
    for d in file["diagnostics"]:
        count += 1
        line = d["range"]["start"]["line"] + 1
        print(f"src/{path}:{line}: [{d['code']}] {d['message']}")

print(f"Замечаний: {count}")
sys.exit(1 if count else 0)
