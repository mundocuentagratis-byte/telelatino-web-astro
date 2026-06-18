import sys
from datetime import datetime, timezone

import generate_news as core


def main() -> int:
    core.reset_report()
    core.write_report("=== TELELATINO Movies ===")
    core.write_report(f"Fecha UTC: {datetime.now(timezone.utc).isoformat()}")

    (core.CONTENT_DIR / "blog").mkdir(parents=True, exist_ok=True)
    (core.CONTENT_DIR / "noticias").mkdir(parents=True, exist_ok=True)

    sources = core.load_json(core.SOURCES_FILE, {})
    group = sources.get("movies")

    if not group:
        core.write_report("[ERROR] No existe el grupo 'movies' en scripts/sources.json")
        return 1

    processed_data = core.load_json(core.PROCESSED_FILE, [])
    processed = core.get_processed_set(processed_data)

    total = core.run_group("movies", group, processed)
    core.save_processed_set(processed)

    core.write_report(f"Total películas publicadas: {total}")
    core.write_report("=== Fin Movies ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
