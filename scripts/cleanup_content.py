import json
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]

BLOG_DIR = ROOT / "src" / "content" / "blog"
NEWS_DIR = ROOT / "src" / "content" / "noticias"
PROCESSED_PATH = ROOT / "scripts" / "processed_articles.json"


DELETE_BLOG_PATTERNS = [
    "15-pruebas-de-amor",
    "antes-del-amor",
    "buffalo-kids",
    "dreams-2023",
    "dreams",
    "el-final-de-oak-street",
    "el-placer-es-mio",
    "estreno-de-habitacion-n-13",
    "habitacion-n-13",
    "la-bola-negra",
    "la-quinta",
    "pelicula-queer-2024",
    "queer-2024",
    "prime-video",
    "sean-penn",
]


KEEP_BLOG_PATTERNS = [
    "como-ver-entretenimiento-digital",
    "toy-story-5",
]


DELETE_NEWS_PATTERNS = [
    "beccacece",
    "cromos",
    "de-burgos",
    "dick-advocaat",
    "el-real-betis",
    "ez-abde",
    "frenkie-de-jong",
    "iker-muniain",
    "koeman",
    "la-tri",
    "saibari",
    "supercopa",
    "rafa-mir",
    "agresion-sexual",
    "agresion",
    "condenado",
    "condena",
    "carcel",
    "prision",
]


KEEP_NEWS_PATTERNS = [
    "novedades-deportivas-online",
    "messi-impulsa",
    "cristiano-ronaldo",
    "zlatko-dalic",
]


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


def should_keep(filename: str, keep_patterns: list[str]) -> bool:
    lower = filename.lower()
    return any(pattern in lower for pattern in keep_patterns)


def should_delete(filename: str, delete_patterns: list[str]) -> bool:
    lower = filename.lower()
    return any(pattern in lower for pattern in delete_patterns)


def delete_matching_files(
    folder: Path,
    delete_patterns: list[str],
    keep_patterns: list[str],
) -> list[Path]:
    deleted_files = []

    if not folder.exists():
        print(f"[WARN] No existe carpeta: {folder}")
        return deleted_files

    for path in sorted(folder.glob("*.md")):
        filename = path.name.lower()

        if should_keep(filename, keep_patterns):
            print(f"[KEEP] {path.relative_to(ROOT)}")
            continue

        if should_delete(filename, delete_patterns):
            print(f"[DELETE] {path.relative_to(ROOT)}")
            path.unlink()
            deleted_files.append(path)
        else:
            print(f"[KEEP] {path.relative_to(ROOT)}")

    return deleted_files


def clean_processed_articles(deleted_files: list[Path]) -> None:
    if not deleted_files:
        return

    processed = load_json(PROCESSED_PATH, {"processed": {}})

    if "processed" not in processed or not isinstance(processed["processed"], dict):
        processed["processed"] = {}

    deleted_relative_paths = {
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in deleted_files
    }

    removed_keys = []

    for key, value in list(processed["processed"].items()):
        generated_file = str(value.get("generatedFile", "")).replace("\\", "/")

        if generated_file in deleted_relative_paths:
            removed_keys.append(key)
            del processed["processed"][key]

    processed["lastCleanup"] = {
        "date": datetime.now(timezone.utc).isoformat(),
        "deletedFiles": sorted(deleted_relative_paths),
        "removedProcessedKeys": len(removed_keys),
    }

    save_json(PROCESSED_PATH, processed)

    print(f"[INFO] Registros eliminados de processed_articles.json: {len(removed_keys)}")


def main() -> int:
    print(">>> LIMPIEZA DE CONTENIDO TELELATINO <<<")

    deleted_blog = delete_matching_files(
        folder=BLOG_DIR,
        delete_patterns=DELETE_BLOG_PATTERNS,
        keep_patterns=KEEP_BLOG_PATTERNS,
    )

    deleted_news = delete_matching_files(
        folder=NEWS_DIR,
        delete_patterns=DELETE_NEWS_PATTERNS,
        keep_patterns=KEEP_NEWS_PATTERNS,
    )

    deleted_files = deleted_blog + deleted_news

    clean_processed_articles(deleted_files)

    print("")
    print(">>> RESUMEN <<<")
    print(f"Películas eliminadas: {len(deleted_blog)}")
    print(f"Noticias eliminadas: {len(deleted_news)}")
    print(f"Total eliminado: {len(deleted_files)}")

    if deleted_files:
        print("")
        print("Archivos eliminados:")
        for path in deleted_files:
            print(f"- {path.relative_to(ROOT)}")

    print("")
    print(">>> LIMPIEZA FINALIZADA <<<")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())