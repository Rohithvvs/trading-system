from pathlib import Path
import re

revs: dict[str, list[str]] = {}
for p in Path("backend/alembic/versions").glob("*.py"):
    t = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^revision(?:\s*:\s*str)?\s*=\s*[\"']([^\"']+)[\"']", t, re.M)
    if not m:
        continue
    rid = m.group(1)
    dm = re.search(r"^down_revision(?:\s*:\s*[^\n=]+)?\s*=\s*(.+?)(?:\n[a-z_]|\Z)", t, re.M | re.S)
    downs: list[str] = []
    if dm:
        downs = re.findall(r"[\"']([^\"']+)[\"']", dm.group(1))
    revs[rid] = downs

pointed: set[str] = set()
for d in revs.values():
    pointed.update(d)
heads = sorted(set(revs) - pointed)
print("HEADS:")
for h in heads:
    print(" ", h, "file=", next(p.name for p, in [(Path("x"),)] ) if False else "")
for h in heads:
    for p in Path("backend/alembic/versions").glob("*.py"):
        if f'"{h}"' in p.read_text(encoding="utf-8", errors="ignore")[:500] or f"'{h}'" in p.read_text(encoding="utf-8", errors="ignore")[:800]:
            if f"revision" in p.read_text(encoding="utf-8", errors="ignore")[:800] and h in p.read_text(encoding="utf-8", errors="ignore"):
                print(" ", h, "->", p.name)
                break
print("total", len(revs), "pointed", len(pointed))
