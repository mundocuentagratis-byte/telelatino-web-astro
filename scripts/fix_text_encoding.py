from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TARGET_EXTENSIONS = {
    ".astro",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".yml",
    ".yaml",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    ".astro",
    ".vercel",
}

REPLACEMENTS = {
    "\u00c3\u00a1": "á",
    "\u00c3\u00a9": "é",
    "\u00c3\u00ad": "í",
    "\u00c3\u00b3": "ó",
    "\u00c3\u00ba": "ú",
    "\u00c3\u0081": "Á",
    "\u00c3\u0089": "É",
    "\u00c3\u008d": "Í",
    "\u00c3\u0093": "Ó",
    "\u00c3\u009a": "Ú",
    "\u00c3\u00b1": "ñ",
    "\u00c3\u0091": "Ñ",
    "\u00c2\u00bf": "¿",
    "\u00c2\u00a1": "¡",
    "\u00c2\u00ba": "º",
    "\u00c2\u00aa": "ª",
    "\u00c2\u00b0": "°",
    "\u00c2\u00a0": " ",
    "\u00e2\u20ac\u201d": "—",
    "\u00e2\u20ac\u201c": "–",
    "\u00e2\u20ac\u0153": "“",
    "\u00e2\u20ac\u009d": "”",
    "\u00e2\u20ac\u2122": "’",
    "\u00e2\u20ac\u00a2": "•",
    "\u00e2\u2013\u00b6": "▶",
}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)

    if parts & SKIP_DIRS:
        return True

    return path.suffix.lower() not in TARGET_EXTENSIONS


def fix_text(text: str) -> str:
    updated = text

    for bad, good in REPLACEMENTS.items():
        updated = updated.replace(bad, good)

    return updated


def main() -> int:
    changed = 0

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        if should_skip(path):
            continue

        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        updated = fix_text(original)

        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(f"[OK] Corregido: {path.relative_to(ROOT)}")

    print(f"Archivos corregidos: {changed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())