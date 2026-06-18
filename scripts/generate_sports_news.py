from datetime import datetime, timezone

import generate_news as core


def main() -> int:
    core.reset_report()

    core.write_report("=== TELELATINO Sports News ===")
    core.write_report(f"Fecha UTC: {datetime.now(timezone.utc).isoformat()}")

    sources = core.load_json(core.SOURCES_FILE, {})
    processed_data = core.load_json(core.PROCESSED_FILE, [])
    processed = core.get_processed_set(processed_data)

    sports_group = sources.get("sports")

    if not isinstance(sports_group, dict):
        core.write_report("[sports] No existe configuración sports en scripts/sources.json")
        core.save_processed_set(processed)
        return 0

    total = core.run_group("sports", sports_group, processed)

    core.save_processed_set(processed)

    core.write_report(f"Total noticias deportivas publicadas: {total}")
    core.write_report("=== Fin Sports ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
