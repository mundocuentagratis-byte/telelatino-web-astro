from datetime import datetime, timezone

import generate_news as core


def main() -> int:
    core.reset_report()

    core.write_report("=== TELELATINO Movies ===")
    core.write_report(f"Fecha UTC: {datetime.now(timezone.utc).isoformat()}")

    sources = core.load_json(core.SOURCES_FILE, {})
    processed_data = core.load_json(core.PROCESSED_FILE, [])
    processed = core.get_processed_set(processed_data)

    movies_group = sources.get("movies")

    if not isinstance(movies_group, dict):
        core.write_report("[movies] No existe configuración movies en scripts/sources.json")
        core.save_processed_set(processed)
        return 0

    total = core.run_group("movies", movies_group, processed)

    core.save_processed_set(processed)

    core.write_report(f"Total películas publicadas: {total}")
    core.write_report("=== Fin Movies ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
