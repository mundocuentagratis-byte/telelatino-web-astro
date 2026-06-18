from datetime import datetime, timezone

import generate_news as core


def main() -> int:
    core.ensure_dirs()
    core.reset_report()

    core.log("=== TELELATINO Sports News ===")
    core.log(f"Fecha UTC: {datetime.now(timezone.utc).isoformat()}")

    sources = core.load_json(core.SOURCES_PATH, {})
    processed = core.load_json(core.PROCESSED_PATH, {"urls": [], "items": []})

    if not isinstance(processed, dict):
        processed = {"urls": [], "items": []}

    processed.setdefault("urls", [])
    processed.setdefault("items", [])

    sports_group = sources.get("sports")

    if not isinstance(sports_group, dict):
        core.log("[sports] No existe configuración sports en scripts/sources.json")
        core.save_json(core.PROCESSED_PATH, processed)
        return 0

    total = core.handle_sports(sports_group, processed)

    core.save_json(core.PROCESSED_PATH, processed)

    core.log(f"Total noticias deportivas publicadas: {total}")
    core.log("=== Fin Sports ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())