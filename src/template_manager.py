"""
template_manager.py — Report template CRUD + history tracking.

Templates: ../templates/<slug>.json  (one file per template)
History:   ../reports/history.json   (last 50 entries, newest-last)
"""
import json
import re
import datetime
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
HISTORY_FILE  = Path(__file__).parent.parent / "reports" / "history.json"
TEMPLATES_DIR.mkdir(exist_ok=True)


# ── Templates ──────────────────────────────────────────────────────────────────

def load_templates() -> list[dict]:
    out = []
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return out


def save_template(name: str, module: str, description: str, prompt: str) -> str:
    slug = _slugify(name)
    base, n = slug, 1
    while (TEMPLATES_DIR / f"{slug}.json").exists():
        slug = f"{base}_{n}"; n += 1
    tpl = {
        "id":          slug,
        "name":        name.strip(),
        "module":      module.upper(),
        "description": description.strip(),
        "prompt":      prompt.strip(),
        "created_at":  _now(),
        "last_run":    None,
        "run_count":   0,
    }
    (TEMPLATES_DIR / f"{slug}.json").write_text(
        json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return slug


def delete_template(template_id: str) -> None:
    p = TEMPLATES_DIR / f"{template_id}.json"
    if p.exists():
        p.unlink()


def update_run(template_id: str) -> None:
    p = TEMPLATES_DIR / f"{template_id}.json"
    if not p.exists():
        return
    tpl = json.loads(p.read_text(encoding="utf-8"))
    tpl["last_run"]  = _now()
    tpl["run_count"] = tpl.get("run_count", 0) + 1
    p.write_text(json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")


# ── History ────────────────────────────────────────────────────────────────────

def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def append_history(file_path: str, question: str, module: str, rows: int, cols: int) -> None:
    history = load_history()
    history.append({
        "timestamp": _now(),
        "file":      file_path,
        "module":    module.upper(),
        "rows":      rows,
        "cols":      cols,
        "question":  question[:100],
    })
    history = history[-50:]
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug[:40] or "template"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")
