import json
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]

BLOG_DIR = ROOT / "src" / "content" / "blog"
NEWS_DIR = ROOT / "src" / "content" / "noticias"

PROCESSED_PATH = ROOT / "scripts" / "processed_articles.json"


KEEP_BLOG_FILES = {
    "como-ver-entretenimiento-digital.md",
}

KEEP_NEWS_FILES = {
    "novedades-deportivas-online.md",
}


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def save_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_generated_files(folder: Path, keep_files: set[str]) -> list[Path]:
    deleted = []

    if not folder.exists():
        print(f"[WARN] No existe la carpeta: {folder}")
        return deleted

    for path in sorted(folder.glob("*.md")):
        if path.name in keep_files:
            print(f"[KEEP] {path.relative_to(ROOT)}")
            continue

        print(f"[DELETE] {path.relative_to(ROOT)}")
        path.unlink()
        deleted.append(path)

    return deleted


def reset_processed_articles(deleted_files: list[Path]) -> None:
    processed = load_json(PROCESSED_PATH, {"processed": {}})

    processed["processed"] = {}
    processed["lastReset"] = {
        "date": datetime.now(timezone.utc).isoformat(),
        "reason": "Reset de artículos generados para aplicar nuevo estilo editorial",
        "deletedFiles": [
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in deleted_files
        ],
    }

    save_json(PROCESSED_PATH, processed)

    print("[OK] scripts/processed_articles.json reiniciado")


def main() -> int:
    print(">>> REINICIANDO CONTENIDO GENERADO TELELATINO <<<")

    deleted_blog = delete_generated_files(BLOG_DIR, KEEP_BLOG_FILES)
    deleted_news = delete_generated_files(NEWS_DIR, KEEP_NEWS_FILES)

    deleted_files = deleted_blog + deleted_news

    reset_processed_articles(deleted_files)

    print("")
    print(">>> RESUMEN <<<")
    print(f"Artículos de películas eliminados: {len(deleted_blog)}")
    print(f"Noticias eliminadas: {len(deleted_news)}")
    print(f"Total eliminado: {len(deleted_files)}")
    print(">>> LIMPIEZA FINALIZADA <<<")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())