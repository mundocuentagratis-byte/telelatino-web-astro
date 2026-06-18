import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTENT_DIRS = [
    ROOT / "src" / "content" / "blog",
    ROOT / "src" / "content" / "noticias",
]

GENERATOR_PATH = ROOT / "scripts" / "generate_news.py"


TEXT_REPLACEMENTS = [
    ("Sinopsis reescrita:", "Sinopsis:"),
    ("Sinopsis reescrita：", "Sinopsis:"),
    ("Sinopsis reescrita", "Sinopsis"),
    ("sinopsis reescrita", "sinopsis"),
    ("SINOPSIS REESCRITA", "SINOPSIS"),
    ("## Sinopsis reescrita:", "## Sinopsis:"),
    ("## Sinopsis reescrita", "## Sinopsis"),
    ("### Sinopsis reescrita:", "### Sinopsis:"),
    ("### Sinopsis reescrita", "### Sinopsis"),
]


SOURCE_LINE_PATTERNS = [
    r"(?im)^\s*fuente consultada\s*:.*$",
    r"(?im)^\s*fuente\s*:.*$",
    r"(?im)^\s*consultado en\s*:.*$",
    r"(?im)^\s*fuente original\s*:.*$",
]


def clean_article_text(text: str) -> str:
    updated = text

    for old, new in TEXT_REPLACEMENTS:
        updated = updated.replace(old, new)

    for pattern in SOURCE_LINE_PATTERNS:
        updated = re.sub(pattern, "", updated)

    updated = re.sub(r"\n{4,}", "\n\n\n", updated)

    return updated


def clean_markdown_files() -> int:
    changed = 0

    for folder in CONTENT_DIRS:
        if not folder.exists():
            print(f"[WARN] No existe: {folder}")
            continue

        for path in sorted(folder.glob("*.md")):
            original = path.read_text(encoding="utf-8")
            updated = clean_article_text(original)

            if updated != original:
                path.write_text(updated, encoding="utf-8")
                changed += 1
                print(f"[OK] Limpio: {path.relative_to(ROOT)}")
            else:
                print(f"[SKIP] Sin cambios: {path.relative_to(ROOT)}")

    return changed


def update_generator_prompt() -> bool:
    if not GENERATOR_PATH.exists():
        print(f"[WARN] No existe: {GENERATOR_PATH}")
        return False

    original = GENERATOR_PATH.read_text(encoding="utf-8")
    updated = original

    updated = updated.replace(
        "- Sinopsis reescrita.",
        "- Sinopsis clara y natural.",
    )

    updated = updated.replace(
        "- Sinopsis reescrita",
        "- Sinopsis clara y natural",
    )

    updated = updated.replace(
        "Sinopsis reescrita",
        "Sinopsis",
    )

    rule = '- Nunca uses la frase "Sinopsis reescrita"; usa solo "Sinopsis".'

    if rule not in updated:
        updated = updated.replace(
            "- No uses saltos de línea sin escapar dentro del JSON.",
            '- No uses saltos de línea sin escapar dentro del JSON.\n'
            '- Nunca uses la frase "Sinopsis reescrita"; usa solo "Sinopsis".',
        )

    if updated != original:
        GENERATOR_PATH.write_text(updated, encoding="utf-8")
        print(f"[OK] Prompt actualizado: {GENERATOR_PATH.relative_to(ROOT)}")
        return True

    print(f"[SKIP] Prompt sin cambios: {GENERATOR_PATH.relative_to(ROOT)}")
    return False


def main() -> int:
    print(">>> CORRIGIENDO CALIDAD DE ARTÍCULOS TELELATINO <<<")

    changed_articles = clean_markdown_files()
    generator_changed = update_generator_prompt()

    print("")
    print(">>> RESUMEN <<<")
    print(f"Artículos corregidos: {changed_articles}")
    print(f"Generador actualizado: {'sí' if generator_changed else 'no'}")
    print(">>> FINALIZADO <<<")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())