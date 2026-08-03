import json
import re
from pathlib import Path

paths = [
    Path(r"C:\Users\k.sai chandra sekhar\.grok\sessions\E%3A%5CLabs%5Ctrading-system\019fc7bb-6ad6-7692-aa46-04f01158bcf5\mcp\call-d1805009-4ffb-4f1c-9711-3d1447df855e-53.json"),
    Path(r"C:\Users\k.sai chandra sekhar\.grok\sessions\E%3A%5CLabs%5Ctrading-system\019fc7bb-6ad6-7692-aa46-04f01158bcf5\mcp\call-e1c63910-a13b-4080-b882-dd819e4420e4-47.json"),
]

best = ""
for p in paths:
    if not p.exists():
        print("missing", p)
        continue
    raw = p.read_text(encoding="utf-8")
    text = ""
    try:
        data = json.loads(raw)
    except Exception as e:
        print("json fail", p.name, e)
        data = None
    if isinstance(data, dict):
        print(p.name, "keys", list(data.keys())[:40])
        for key in ("content", "content_preview", "text", "result"):
            val = data.get(key)
            if isinstance(val, str) and len(val) > len(text):
                text = val
            elif isinstance(val, dict):
                for k2 in ("content", "content_preview", "text"):
                    v2 = val.get(k2)
                    if isinstance(v2, str) and len(v2) > len(text):
                        text = v2
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        for k2 in ("content", "content_preview", "text", "text"):
                            v2 = item.get(k2)
                            if isinstance(v2, str) and len(v2) > len(text):
                                text = v2
    # Fallback: locate "content": "..." string and decode via JSON
    if len(text) < 1000:
        for m in re.finditer(r'"(?:content|content_preview)"\s*:\s*"', raw):
            start = m.end() - 1  # at opening quote
            try:
                val, _ = json.JSONDecoder().raw_decode(raw[start:])
                if isinstance(val, str) and len(val) > len(text):
                    text = val
            except Exception:
                continue
    print(p.name, "extracted", len(text))
    if len(text) > len(best):
        best = text

out = Path(r"E:\Labs\trading-system\scratch\all_res_full.md")
# unescape common markdown bold markers left from Google export if present
best = best.replace("\\*", "*").replace("\\#", "#").replace("\\-", "-")
out.write_text(best, encoding="utf-8")
print("wrote", out, "chars", len(best))

# Print outline of headings
for line in best.splitlines():
    s = line.strip()
    if s.startswith("#") or "Document 0" in s or s.startswith("## "):
        print(s[:140])
