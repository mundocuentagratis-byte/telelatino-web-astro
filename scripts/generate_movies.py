from datetime import datetime, timezone

import generate_news as core


def main() -> int:
    core.ensure_dirs()
    core.ensure_reports_dir()

    core.log("=== TELELATINO Movies ===")
    core.log(f"Fecha UTC: {datetime.now(timezone.utc).isoformat()}")

    sources = core.load_json(core.SOURCES_PATH, {})
    processed = core.load_json(core.PROCESSED_PATH, {"urls": [], "items": []})

    if not isinstance(processed, dict):
        processed = {"urls": [], "items": []}

    processed.setdefault("urls", [])
    processed.setdefault("items", [])

    movies_group = sources.get("movies")

    if not isinstance(movies_group, dict):
        core.log("[movies] No existe configuración movies en scripts/sources.json")
        core.save_json(core.PROCESSED_PATH, processed)
        return 0

    total = core.handle_movies(movies_group, processed)

    core.save_json(core.PROCESSED_PATH, processed)

    core.log(f"Total películas publicadas: {total}")
    core.log("=== Fin Movies ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())