import json
import os
import re
import hashlib
import unicodedata
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from google import genai
except Exception:
    genai = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from mistralai import Mistral
except Exception:
    Mistral = None


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

SOURCES_FILE = SCRIPTS_DIR / "sources.json"
SOURCES_PATH = SOURCES_FILE

PROCESSED_FILE = SCRIPTS_DIR / "processed_articles.json"
PROCESSED_PATH = PROCESSED_FILE

REPORTS_DIR = SCRIPTS_DIR / "reports"
REPORT_FILE = REPORTS_DIR / "auto_news_report.txt"
REPORT_PATH = REPORT_FILE

CONTENT_DIR = ROOT / "src" / "content"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
COHERE_MODEL = os.getenv("COHERE_MODEL", "command-r")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
}

BLOCKED_TOPIC_WORDS = {
    "abuso",
    "agresión sexual",
    "agresion sexual",
    "violación",
    "violacion",
    "cárcel",
    "carcel",
    "prisión",
    "prision",
    "condena",
    "condenado",
    "fallece",
    "falleció",
    "murió",
    "muerte",
    "asesinato",
    "violencia",
    "apuesta",
    "apuestas",
    "casino",
    "gambling",
    "cromos",
    "onlyfans",
}

BAD_MOVIE_TITLE_WORDS = {
    "cartelera",
    "cartelera y entrada",
    "entrada",
    "entradas",
    "sesiones",
    "trailer",
    "tráiler",
    "videos",
    "vídeos",
    "reparto",
    "críticas",
    "criticas",
    "fotos",
    "streaming",
    "serie",
    "series",
    "temporada",
    "netflix cancela",
    "cancela",
    "crunchyroll",
    "anime",
    "animes",
    "prime video",
    "disney+",
    "hbo",
    "max",
    "apple tv",
}

BAD_MOVIE_PATH_PARTS = {
    "/sesiones/",
    "/videos/",
    "/video/",
    "/trailer/",
    "/trailers/",
    "/criticas/",
    "/critica/",
    "/fotos/",
    "/streaming/",
    "/series/",
    "/serie/",
    "/tv/",
}

MOVIE_NEWS_BLOCK_WORDS = {
    "streaming",
    "netflix",
    "crunchyroll",
    "anime",
    "animes",
    "serie",
    "series",
    "temporada",
    "temporadas",
    "cancelada",
    "cancela",
    "cancelan",
    "prime video",
    "disney",
    "hbo",
    "max",
    "apple tv",
}

MOVIE_NEWS_REQUIRED_WORDS = {
    "película",
    "pelicula",
    "cine",
    "estreno",
    "estrena",
    "tráiler",
    "trailer",
    "rodaje",
    "taquilla",
    "reparto",
}

SPORTS_TEXT_HINTS = {
    "futbol",
    "fútbol",
    "mundial",
    "copa",
    "liga",
    "champions",
    "europa league",
    "conference league",
    "barcelona",
    "barça",
    "barca",
    "real madrid",
    "atletico",
    "atlético",
    "seleccion",
    "selección",
    "partido",
    "jugador",
    "equipo",
    "entrenador",
    "fichaje",
    "lesion",
    "lesión",
    "debut",
    "goleador",
    "delantero",
    "defensa",
    "portero",
    "centrocampista",
    "balonmano",
    "baloncesto",
    "tenis",
    "formula 1",
    "fórmula 1",
    "motogp",
    "ciclismo",
    "tour de francia",
    "clasificacion",
    "clasificación",
}

NON_SPORTS_TEXT_HINTS = {
    "tecnologia",
    "tecnología",
    "auricular",
    "traductor",
    "viajes",
    "amazon",
    "oferta",
    "descuento",
    "compra",
    "smartphone",
    "movil",
    "móvil",
    "horoscopo",
    "horóscopo",
    "receta",
    "salud",
    "moda",
    "television",
    "televisión",
}

REPORT_LINES: list[str] = []


def ensure_dirs() -> None:
    (CONTENT_DIR / "blog").mkdir(parents=True, exist_ok=True)
    (CONTENT_DIR / "noticias").mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def reset_report() -> None:
    ensure_dirs()
    REPORT_LINES.clear()
    REPORT_FILE.write_text("", encoding="utf-8")


def write_report(message: str) -> None:
    print(message)
    REPORT_LINES.append(message)
    ensure_reports_dir()
    REPORT_FILE.write_text("\n".join(REPORT_LINES) + "\n", encoding="utf-8")


def log(message: str) -> None:
    write_report(message)


def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(value: str) -> str:
    if not value:
        return ""

    text = BeautifulSoup(str(value), "html.parser").get_text(" ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_text(value: str) -> str:
    value = strip_accents(value or "")
    value = value.lower()
    value = re.sub(r"[^a-z0-9ñ\s-]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def slugify(value: str, max_length: int = 88) -> str:
    value = normalize_text(value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    value = re.sub(r"-+", "-", value)

    if not value:
        value = "articulo"

    return value[:max_length].strip("-")


def url_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:12]


def request_text(url: str, timeout: int = 25) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def absolute_url(base_url: str, maybe_url: str) -> str:
    if not maybe_url:
        return ""
    return urljoin(base_url, maybe_url.strip())


def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def is_blocked_topic(text: str) -> bool:
    normalized = normalize_text(text)
    return any(word in normalized for word in BLOCKED_TOPIC_WORDS)


def should_skip_paragraph(text: str) -> bool:
    normalized = normalize_text(text)

    if len(normalized) < 45:
        return True

    skip_phrases = [
        "suscribete",
        "newsletter",
        "publicidad",
        "cookies",
        "aceptar cookies",
        "leer tambien",
        "tambien puedes leer",
        "comparte en",
        "todos los derechos reservados",
        "iniciar sesion",
        "registrate",
        "haz clic",
    ]

    return any(phrase in normalized for phrase in skip_phrases)


def extract_meta_content(soup: BeautifulSoup, selectors: list[tuple[str, str]]) -> str:
    for attr_name, attr_value in selectors:
        tag = soup.find("meta", attrs={attr_name: attr_value})

        if tag and tag.get("content"):
            return clean_text(tag.get("content", ""))

    return ""


def extract_meta_image(soup: BeautifulSoup, base_url: str) -> str:
    selectors = [
        ("property", "og:image"),
        ("name", "twitter:image"),
        ("property", "og:image:secure_url"),
    ]

    for attr_name, attr_value in selectors:
        tag = soup.find("meta", attrs={attr_name: attr_value})

        if tag and tag.get("content"):
            image_url = absolute_url(base_url, tag["content"])

            if image_url:
                return image_url

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        alt = normalize_text(img.get("alt", ""))

        if not src:
            continue

        src_norm = normalize_text(src)

        if any(bad in src_norm for bad in ["logo", "icon", "sprite", "avatar", "blank"]):
            continue

        if any(bad in alt for bad in ["logo", "icon", "avatar"]):
            continue

        return absolute_url(base_url, src)

    return ""


def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")

    if h1:
        title = clean_text(h1.get_text(" "))

        if title:
            return title

    meta_title = extract_meta_content(
        soup,
        [
            ("property", "og:title"),
            ("name", "twitter:title"),
        ],
    )

    if meta_title:
        return meta_title

    if soup.title:
        return clean_text(soup.title.get_text(" "))

    return ""


def extract_description(soup: BeautifulSoup) -> str:
    return extract_meta_content(
        soup,
        [
            ("name", "description"),
            ("property", "og:description"),
            ("name", "twitter:description"),
        ],
    )


def extract_article_data(url: str) -> dict:
    html = request_text(url)
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
        tag.decompose()

    title = extract_title(soup)
    description = extract_description(soup)
    image = extract_meta_image(soup, url)

    containers = soup.find_all(["article", "main"])
    paragraphs: list[str] = []

    if containers:
        for container in containers:
            for p in container.find_all(["p", "li"]):
                paragraph = clean_text(p.get_text(" "))

                if paragraph and not should_skip_paragraph(paragraph):
                    paragraphs.append(paragraph)
    else:
        for p in soup.find_all(["p", "li"]):
            paragraph = clean_text(p.get_text(" "))

            if paragraph and not should_skip_paragraph(paragraph):
                paragraphs.append(paragraph)

    seen = set()
    unique_paragraphs: list[str] = []

    for paragraph in paragraphs:
        key = normalize_text(paragraph)[:140]

        if key in seen:
            continue

        seen.add(key)
        unique_paragraphs.append(paragraph)

    text_parts = []

    if description:
        text_parts.append(description)

    text_parts.extend(unique_paragraphs[:30])

    return {
        "title": title,
        "url": url,
        "description": description,
        "text": "\n\n".join(text_parts).strip(),
        "image": image,
    }


def extract_date_from_url(url: str) -> date | None:
    patterns = [
        r"/(20\d{2})/(\d{1,2})/(\d{1,2})/",
        r"/(20\d{2})-(\d{1,2})-(\d{1,2})(?:/|-)",
        r"(20\d{2})-(\d{1,2})-(\d{1,2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)

        if not match:
            continue

        year, month, day = map(int, match.groups())

        try:
            return date(year, month, day)
        except ValueError:
            continue

    return None


def is_recent_news_url(url: str, max_age_days: int) -> bool:
    article_date = extract_date_from_url(url)

    if not article_date:
        return False

    today = datetime.now(timezone.utc).date()
    min_date = today - timedelta(days=max_age_days)

    return min_date <= article_date <= today + timedelta(days=1)


def looks_like_sports_article(title: str, url: str, text: str = "") -> bool:
    normalized = normalize_text(f"{title} {url} {text[:700]}")

    if any(bad in normalized for bad in NON_SPORTS_TEXT_HINTS):
        return False

    return any(hint in normalized for hint in SPORTS_TEXT_HINTS)


def is_latest_listing_url(url: str) -> bool:
    normalized_url = url.lower()
    return (
        "/loultimo" in normalized_url
        or "/ultimo" in normalized_url
        or "/ultima-hora" in normalized_url
        or "/ultimas" in normalized_url
    )


def movie_title_is_invalid(title: str) -> bool:
    normalized = normalize_text(title)

    if not normalized or len(normalized) < 3:
        return True

    return any(word in normalized for word in BAD_MOVIE_TITLE_WORDS)


def extract_movie_release_year(text: str) -> int | None:
    if not text:
        return None

    compact = clean_text(text)[:7000]
    lowered = normalize_text(compact)

    patterns = [
        r"fecha de estreno[^\d]*(20\d{2})",
        r"estreno en cines[^\d]*(20\d{2})",
        r"estreno[^\d]*(20\d{2})",
        r"estrena[^\d]*(20\d{2})",
        r"en cartelera[^\d]*(20\d{2})",
        r"proximamente[^\d]*(20\d{2})",
        r"próximamente[^\d]*(20\d{2})",
        r"lanzamiento[^\d]*(20\d{2})",
        r"\b(20\d{2})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)

        if match:
            return int(match.group(1))

    return None


def get_listing_links(url: str) -> list[dict]:
    html = request_text(url)
    soup = BeautifulSoup(html, "html.parser")
    links: list[dict] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        link = absolute_url(url, href)
        title = clean_text(anchor.get_text(" "))

        if not title:
            title = clean_text(anchor.get("title", ""))

        if not link:
            continue

        links.append(
            {
                "title": title,
                "url": link,
            }
        )

    return links


def get_sports_candidates(group: dict) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    max_age_days = int(group.get("maxAgeDays", 7))
    requires_image = bool(group.get("requiresImage", True))
    source_name = group.get("sourceName", "")
    category = group.get("category", "Deportes")
    target_collection = group.get("targetCollection", "noticias")

    for listing_url in group.get("urls", []):
        listing_is_latest = is_latest_listing_url(listing_url)

        try:
            links = get_listing_links(listing_url)
        except Exception as exc:
            write_report(f"[sports] No se pudo leer listado {listing_url}: {exc}")
            continue

        for item in links:
            url = item.get("url", "")
            title_hint = item.get("title", "")
            parsed = urlparse(url)

            if url in seen:
                continue

            if parsed.netloc and urlparse(listing_url).netloc not in parsed.netloc:
                continue

            if not looks_like_sports_article(title_hint, url):
                continue

            article_date = extract_date_from_url(url)

            if article_date:
                if not is_recent_news_url(url, max_age_days=max_age_days):
                    continue
            else:
                if not listing_is_latest:
                    continue

            if is_blocked_topic(f"{title_hint} {url}"):
                continue

            try:
                data = extract_article_data(url)
            except Exception as exc:
                write_report(f"[sports] No se pudo extraer {url}: {exc}")
                continue

            title = data.get("title") or title_hint
            text = data.get("text", "")
            image = data.get("image", "")

            if not title or len(text) < 300:
                continue

            if not looks_like_sports_article(title, url, text):
                continue

            if is_blocked_topic(f"{title} {text[:800]}"):
                continue

            if requires_image and not image:
                continue

            seen.add(url)

            candidates.append(
                {
                    "title": title,
                    "url": url,
                    "text": text,
                    "image": image,
                    "sourceName": source_name,
                    "category": category,
                    "targetCollection": target_collection,
                    "priority": 0 if listing_is_latest else 1,
                }
            )

    candidates.sort(key=lambda item: (item.get("priority", 9), item.get("title", "")))

    return candidates


def is_sensacine_movie_detail_url(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()

    if "sensacine.com" not in domain:
        return False

    if any(bad in path for bad in BAD_MOVIE_PATH_PARTS):
        return False

    return "/peliculas/pelicula-" in path


def is_sensacine_movie_news_url(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()

    if "sensacine.com" not in domain:
        return False

    if any(bad in path for bad in BAD_MOVIE_PATH_PARTS):
        return False

    return "/noticias/cine/noticia-" in path or "/noticias/noticia-" in path


def is_movie_detail_url(url: str) -> bool:
    return is_sensacine_movie_detail_url(url)


def movie_news_is_valid(title: str, text: str, url: str) -> bool:
    normalized = normalize_text(f"{title} {text[:1200]} {url}")

    if any(word in normalized for word in MOVIE_NEWS_BLOCK_WORDS):
        return False

    if not any(word in normalized for word in MOVIE_NEWS_REQUIRED_WORDS):
        return False

    return True


def get_movie_identity(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r"\s*-\s*SensaCine.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\|\s*SensaCine.*$", "", title, flags=re.IGNORECASE)
    return title.strip()


def get_movies_candidates(group: dict) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    category = group.get("category", "Películas")
    target_collection = group.get("targetCollection", "blog")
    requires_image = bool(group.get("requiresImage", True))
    only_release_year = int(group.get("onlyReleaseYear", group.get("minReleaseYear", 2026)))

    for listing_url in group.get("urls", []):
        listing_url_norm = listing_url.lower()
        listing_is_releases = "/peliculas/estrenos" in listing_url_norm
        listing_is_news = "/noticias" in listing_url_norm

        try:
            links = get_listing_links(listing_url)
        except Exception as exc:
            write_report(f"[movies] No se pudo leer listado {listing_url}: {exc}")
            continue

        for item in links:
            url = item.get("url", "")

            if url in seen:
                continue

            is_release_card = is_sensacine_movie_detail_url(url)
            is_movie_news = listing_is_news and is_sensacine_movie_news_url(url)

            if not is_release_card and not is_movie_news:
                continue

            try:
                data = extract_article_data(url)
            except Exception as exc:
                write_report(f"[movies] No se pudo extraer {url}: {exc}")
                continue

            title = get_movie_identity(data.get("title", "") or item.get("title", ""))
            text = data.get("text", "")
            image = data.get("image", "")

            if movie_title_is_invalid(title):
                continue

            if len(text) < 250:
                continue

            if requires_image and not image:
                continue

            release_year = extract_movie_release_year(f"{title}\n{text}\n{url}")

            if release_year != only_release_year:
                write_report(
                    f"[movies] Saltado porque no es estreno {only_release_year}: "
                    f"{title} ({release_year})"
                )
                continue

            if is_movie_news and not movie_news_is_valid(title, text, url):
                write_report(f"[movies] Saltado noticia no apta para películas: {title}")
                continue

            seen.add(url)

            candidates.append(
                {
                    "title": title,
                    "url": url,
                    "text": text,
                    "image": image,
                    "sourceName": "SensaCine",
                    "category": category,
                    "targetCollection": target_collection,
                    "releaseYear": release_year,
                    "contentKind": "estreno" if is_release_card else "noticia_cine",
                    "priority": 0 if is_release_card else 1,
                }
            )

    candidates.sort(key=lambda item: (item.get("priority", 9), item.get("title", "")))

    return candidates


def get_movie_candidates(group: dict, processed=None) -> list[dict]:
    return get_movies_candidates(group)


def extract_frontmatter_value(text: str, key: str) -> str:
    pattern = rf"^{re.escape(key)}:\s*(.+?)\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)

    if not match:
        return ""

    value = match.group(1).strip().strip('"').strip("'")
    return value


def extract_pub_date(text: str) -> date | None:
    value = extract_frontmatter_value(text, "pubDate")

    if not value:
        return None

    value = value.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", value)

        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None

    return None


def post_matches_category(path: Path, category: str, target_collection: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False

    normalized = normalize_text(text[:2500])
    category_norm = normalize_text(category)

    if target_collection == "blog" or category_norm == "peliculas":
        return (
            "category peliculas" in normalized
            or "category peliculas" in normalized.replace(":", "")
            or "sensacine" in normalized
            or "youtubevideoid" in normalized
        )

    if target_collection == "noticias" or category_norm == "deportes":
        return "category deportes" in normalized or "mundo deportivo" in normalized

    return category_norm in normalized


def count_existing_posts(group: dict) -> int:
    target_collection = group.get("targetCollection", "blog")
    category = group.get("category", "")
    collection_dir = CONTENT_DIR / target_collection

    if not collection_dir.exists():
        return 0

    count = 0

    for path in list(collection_dir.glob("*.md")) + list(collection_dir.glob("*.mdx")):
        if post_matches_category(path, category, target_collection):
            count += 1

    return count


def count_posts_today(group: dict) -> int:
    target_collection = group.get("targetCollection", "blog")
    category = group.get("category", "")
    collection_dir = CONTENT_DIR / target_collection
    today = datetime.now(timezone.utc).date()

    if not collection_dir.exists():
        return 0

    count = 0

    for path in list(collection_dir.glob("*.md")) + list(collection_dir.glob("*.mdx")):
        if not post_matches_category(path, category, target_collection):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        if extract_pub_date(text) == today:
            count += 1

    return count


def get_dynamic_daily_limit(group: dict) -> int:
    target_collection = group.get("targetCollection", "")
    category = normalize_text(group.get("category", ""))

    existing = count_existing_posts(group)
    initial_target = int(group.get("initialTarget", 0) or 0)

    if initial_target > 0 and existing < initial_target:
        return max(0, initial_target - existing)

    if target_collection == "blog" or category == "peliculas":
        after_initial = int(group.get("dailyLimitAfterInitial", 1))
        return max(0, after_initial)

    # Para deportes: cada ejecución publica 1 o 2 noticias recientes si hay candidatos.
    per_run = int(group.get("dailyLimit", 2))
    return max(0, per_run)


def editorial_seed_options(candidate: dict) -> dict:
    seed = f"{candidate.get('url', '')}-{datetime.now(timezone.utc).date().isoformat()}"
    number = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)

    movie_hooks = [
        "un arranque directo que presente por qué esta película puede interesar al público",
        "una entrada con tono de recomendación, sin exagerar ni vender humo",
        "una introducción que ubique al lector antes de hablar de la historia",
        "un inicio cercano, como alguien que comenta un estreno que vale la pena mirar",
    ]

    sports_hooks = [
        "un arranque con el dato más importante de la noticia",
        "una entrada con lectura deportiva clara y sin dramatizar",
        "un inicio que explique por qué el tema está moviendo conversación",
        "un primer párrafo directo, como una nota de actualidad deportiva",
    ]

    return {
        "movie_hook": movie_hooks[number % len(movie_hooks)],
        "sports_hook": sports_hooks[number % len(sports_hooks)],
    }


def build_prompt(candidate: dict, group: dict) -> str:
    title = candidate.get("title", "").strip()
    url = candidate.get("url", "").strip()
    text = candidate.get("text", "").strip()
    category = group.get("category", "Entretenimiento")
    source_name = group.get("sourceName", "").strip() or candidate.get("sourceName", "")
    target_collection = group.get("targetCollection", "").strip()
    seed_options = editorial_seed_options(candidate)

    is_movie = target_collection == "blog" or normalize_text(category) == "peliculas"
    is_sports = target_collection == "noticias" or normalize_text(category) == "deportes"

    if is_movie:
        article_type = "película o estreno de cine"
        word_range = "750 a 1000 palabras"
        intro_style = seed_options["movie_hook"]
        editorial_focus = """
Este artículo es para la sección de Películas de TELELATINO.

Reglas especiales:
- El tema debe tratarse como película, estreno o noticia de cine.
- No escribas sobre series, anime, Crunchyroll, Netflix, streaming ni plataformas salvo que sea un dato secundario de una película de cine.
- No escribas “Sinopsis reescrita”.
- No inventes que la película está disponible en TELELATINO.
- No inventes reparto, fecha, plataforma, taquilla ni detalles que no estén en el texto.
- Si hay información de estreno, debe quedar clara y natural.
- La redacción debe sentirse humana, no una ficha técnica.

Usa subtítulos naturales y variados según el contenido:
- De qué trata la película
- Por qué este estreno puede llamar la atención
- Qué se sabe de su llegada
- El tono de la historia
- Una película para tener en el radar
- Qué esperar antes de verla
- El detalle que puede marcar la diferencia
"""
    elif is_sports:
        article_type = "noticia deportiva"
        word_range = "650 a 900 palabras"
        intro_style = seed_options["sports_hook"]
        editorial_focus = """
Este artículo es para la sección de Noticias deportivas de TELELATINO.

Reglas especiales:
- Debe sentirse como una nota deportiva escrita por un redactor real.
- No inventes declaraciones, resultados, lesiones, fichajes o fechas si no aparecen.
- No uses siempre los mismos subtítulos.
- Explica qué pasó, por qué importa y qué lectura deja para el aficionado.
"""
    else:
        article_type = "artículo informativo"
        word_range = "700 a 950 palabras"
        intro_style = "una introducción clara, humana y útil"
        editorial_focus = """
Este artículo debe sentirse como una nota informativa clara, útil y humana.
Evita estructuras repetitivas y subtítulos genéricos.
No inventes datos que no estén en la información entregada.
"""

    return f"""
Eres el redactor editorial de TELELATINO, una web enfocada en entretenimiento para Android, películas, deportes, noticias y contenido digital.

Tu tarea es convertir la información entregada en un artículo original, útil y natural para lectores reales.

DATOS DE ENTRADA:
Título original: {title}
Fuente: {source_name}
URL de referencia: {url}
Categoría: {category}
Tipo de artículo: {article_type}

INFORMACIÓN DISPONIBLE:
{text[:9000]}

ESTILO EDITORIAL TELELATINO:
{editorial_focus}

DIRECCIÓN DE ESTE ARTÍCULO:
- Usa {intro_style}.
- El artículo debe tener personalidad propia, no parecer una plantilla repetida.
- Mantén una línea editorial coherente con TELELATINO, pero evita que todos los artículos suenen iguales.

REGLAS DE CALIDAD:
- Escribe en español neutro.
- Usa una voz humana, profesional y cercana.
- Evita frases robóticas como “en este artículo exploraremos”, “en conclusión”, “sin duda alguna”, “cabe destacar que” repetida muchas veces.
- No uses emojis dentro del artículo.
- No uses mayúsculas excesivas.
- No escribas contenido sensacionalista.
- No inventes datos.
- No menciones que el texto fue reescrito.
- No menciones inteligencia artificial.
- No pongas “Fuente consultada”.
- No pongas enlaces externos dentro del cuerpo.
- El contenido debe tener aproximadamente {word_range}, pero si la información disponible no alcanza, prioriza calidad y claridad antes que relleno.

ESTRUCTURA RECOMENDADA:
1. Una introducción natural de 2 o 3 párrafos.
2. Entre 3 y 5 secciones con subtítulos H2 variados y humanos.
3. Un cierre breve, natural, conectado con TELELATINO, sin sonar forzado.

IMPORTANTE PARA EL CUERPO:
- Usa Markdown.
- Usa subtítulos con "##".
- No uses "#".
- No uses el subtítulo “Sinopsis reescrita”.
- No uses el subtítulo “Fuente consultada”.
- No repitas el título exacto dentro de todos los subtítulos.

DEVUELVE ÚNICAMENTE JSON VÁLIDO con esta estructura exacta:
{{
  "title": "Título SEO natural, máximo 70 caracteres",
  "description": "Meta descripción clara, máximo 155 caracteres",
  "body": "Artículo completo en Markdown",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "imageAlt": "Texto alternativo claro para la imagen"
}}
""".strip()


def parse_json_response(text: str) -> dict:
    if not text:
        raise ValueError("Respuesta vacía de la IA")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1], strict=False)

        raise


def remove_markdown_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)


def sanitize_body(body: str) -> str:
    body = body or ""
    body = body.replace("\r\n", "\n")
    body = remove_markdown_links(body)

    replacements = {
        "Sinopsis reescrita:": "Sinopsis:",
        "Sinopsis reescrita": "Sinopsis",
        "Fuente consultada:": "",
        "Fuente consultada": "",
        "Fuentes consultadas:": "",
        "Fuentes consultadas": "",
        "En este artículo exploraremos": "En esta nota revisamos",
        "En conclusión,": "Para cerrar,",
        "En conclusión": "Para cerrar",
        "Cabe destacar que": "También es importante señalar que",
        "Sin duda alguna": "Sin exagerar",
    }

    for bad, good in replacements.items():
        body = body.replace(bad, good)

    lines = []
    skip_next = False

    for line in body.split("\n"):
        stripped = line.strip()

        if not stripped:
            lines.append("")
            continue

        normalized = normalize_text(stripped)

        if normalized in {"fuente", "fuentes", "fuente consultada", "fuentes consultadas"}:
            skip_next = True
            continue

        if skip_next and ("http" in stripped or len(stripped) < 120):
            skip_next = False
            continue

        skip_next = False

        if stripped.startswith("# "):
            stripped = "## " + stripped[2:].strip()
        elif stripped.startswith("### "):
            stripped = "## " + stripped[4:].strip()

        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            heading = heading.replace("Sinopsis reescrita", "Sinopsis")
            stripped = "## " + heading

        lines.append(stripped)

    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return body


def normalize_article_data(data: dict, candidate: dict) -> dict:
    title = clean_text(str(data.get("title", "")))[:90]
    description = clean_text(str(data.get("description", "")))[:180]
    body = str(data.get("body", "")).strip()

    if not title:
        title = clean_text(candidate.get("title", ""))[:90]

    if not description:
        description = clean_text(candidate.get("text", ""))[:155]

    tags = data.get("tags", [])

    if not isinstance(tags, list):
        tags = []

    clean_tags: list[str] = []

    for tag in tags:
        tag_text = clean_text(str(tag))

        if not tag_text:
            continue

        if tag_text.lower() in {t.lower() for t in clean_tags}:
            continue

        clean_tags.append(tag_text[:30])

        if len(clean_tags) >= 5:
            break

    if not clean_tags:
        clean_tags = [candidate.get("category", "Entretenimiento"), "TELELATINO"]

    image_alt = clean_text(str(data.get("imageAlt", "")))

    if not image_alt:
        image_alt = f"Imagen relacionada con {title}"

    body = sanitize_body(body)

    if len(body) < 900:
        raise ValueError("El cuerpo generado es demasiado corto o vacío")

    return {
        "title": title,
        "description": description,
        "body": body,
        "tags": clean_tags,
        "imageAlt": image_alt[:160],
    }


def is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()

    return any(
        phrase in text
        for phrase in [
            "quota",
            "insufficient_quota",
            "rate limit",
            "rate_limit",
            "too many requests",
            "429",
            "billing",
            "credits",
            "exceeded",
        ]
    )


def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("No existe GEMINI_API_KEY.")

    if genai is None:
        raise RuntimeError("No está instalado google-genai.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    text = getattr(response, "text", "") or ""

    if not text.strip():
        raise RuntimeError("Gemini no devolvió texto.")

    return text.strip()


def call_openai_provider(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("No existe OPENAI_API_KEY.")

    if OpenAI is None:
        raise RuntimeError("No está instalado openai.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Eres un redactor SEO. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.45,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or ""


def call_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("No existe GROQ_API_KEY.")

    if OpenAI is None:
        raise RuntimeError("No está instalado openai.")

    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Eres un redactor SEO. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.45,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or ""


def call_mistral(prompt: str) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("No existe MISTRAL_API_KEY.")

    if Mistral is None:
        raise RuntimeError("No está instalado mistralai.")

    client = Mistral(api_key=MISTRAL_API_KEY)
    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Eres un redactor SEO. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.45,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or ""


def call_cohere(prompt: str) -> str:
    if not COHERE_API_KEY:
        raise RuntimeError("No existe COHERE_API_KEY.")

    url = "https://api.cohere.com/v2/chat"

    headers = {
        "Authorization": f"Bearer {COHERE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": COHERE_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Eres un redactor SEO. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.45,
        "response_format": {
            "type": "json_object",
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=75)

    if response.status_code >= 400:
        raise RuntimeError(
            f"Cohere error {response.status_code}: {response.text[:1200]}"
        )

    data = response.json()
    message = data.get("message", {})
    content = message.get("content", "")

    if isinstance(content, list):
        pieces = []

        for item in content:
            if isinstance(item, dict):
                pieces.append(item.get("text", "") or item.get("content", "") or "")
            else:
                pieces.append(str(item))

        text = "".join(pieces).strip()

        if text:
            return text

    if isinstance(content, str) and content.strip():
        return content.strip()

    if data.get("text"):
        return str(data["text"]).strip()

    raise RuntimeError(
        f"Cohere no devolvió texto válido: {json.dumps(data)[:1000]}"
    )


def call_ai_provider(provider: str, prompt: str) -> str:
    provider = provider.lower()

    if provider == "gemini":
        return call_gemini(prompt)

    if provider == "openai":
        return call_openai_provider(prompt)

    if provider == "groq":
        return call_groq(prompt)

    if provider == "mistral":
        return call_mistral(prompt)

    if provider == "cohere":
        return call_cohere(prompt)

    raise RuntimeError(f"Proveedor no soportado: {provider}")


def rotate_list(items: list[str], seed: str) -> list[str]:
    if not items:
        return []

    number = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    offset = number % len(items)

    return items[offset:] + items[:offset]


def get_ai_provider_order(group: dict, candidate: dict) -> list[str]:
    category = normalize_text(group.get("category", ""))
    target_collection = group.get("targetCollection", "")

    if target_collection == "blog" or category == "peliculas":
        base_order = ["mistral", "cohere", "gemini", "groq", "openai"]
    elif target_collection == "noticias" or category == "deportes":
        base_order = ["groq", "mistral", "cohere", "gemini", "openai"]
    else:
        base_order = ["mistral", "cohere", "groq", "gemini", "openai"]

    seed = (
        f"{datetime.now(timezone.utc).date().isoformat()}-"
        f"{candidate.get('url', '')}-"
        f"{candidate.get('title', '')}"
    )

    return rotate_list(base_order, seed)


def generate_with_ai_router(candidate: dict, group: dict) -> dict:
    prompt = build_prompt(candidate, group)
    errors: list[str] = []

    for provider in get_ai_provider_order(group, candidate):
        try:
            write_report(
                f"[IA] Probando proveedor {provider}: "
                f"{candidate.get('title', '')[:80]}"
            )

            raw = call_ai_provider(provider, prompt)
            parsed = parse_json_response(raw)
            article = normalize_article_data(parsed, candidate)
            article["provider"] = provider

            write_report(f"[IA] Artículo generado con {provider}")

            return article
        except Exception as exc:
            label = "cuota" if is_quota_error(exc) else "error"
            message = f"[IA] {provider} falló ({label}): {str(exc)[:500]}"
            write_report(message)
            errors.append(message)
            continue

    raise RuntimeError(
        "Todos los proveedores de IA fallaron. " + " | ".join(errors[-3:])
    )


def meaningful_words(value: str) -> set[str]:
    normalized = normalize_text(value)
    words = {word for word in normalized.split() if len(word) >= 4}

    stopwords = {
        "pelicula",
        "peliculas",
        "trailer",
        "oficial",
        "estreno",
        "2026",
        "cine",
        "cines",
        "nuevo",
        "nueva",
        "spanish",
        "latino",
        "subtitulado",
        "doblado",
        "sensacine",
        "telelatino",
    }

    return words - stopwords


def trailer_matches_movie(
    movie_title: str,
    video_title: str,
    release_year: int | None,
) -> bool:
    movie_words = meaningful_words(movie_title)
    video_words = meaningful_words(video_title)
    normalized_video = normalize_text(video_title)

    if "trailer" not in normalized_video and "avance" not in normalized_video:
        return False

    if not movie_words:
        return False

    matches = len(movie_words & video_words)
    required = 1 if len(movie_words) <= 2 else 2

    if matches < required:
        return False

    if release_year:
        years = re.findall(r"\b(20\d{2})\b", video_title)

        if years and str(release_year) not in years:
            return False

    return True


def search_youtube_trailer(
    movie_title: str,
    release_year: int | None = None,
) -> dict | None:
    if not YOUTUBE_API_KEY:
        write_report("[YouTube] No existe YOUTUBE_API_KEY; se omite tráiler.")
        return None

    query_parts = [movie_title, "trailer oficial"]

    if release_year:
        query_parts.append(str(release_year))

    params = {
        "part": "snippet",
        "q": " ".join(query_parts),
        "type": "video",
        "maxResults": 8,
        "key": YOUTUBE_API_KEY,
        "relevanceLanguage": "es",
        "safeSearch": "moderate",
    }

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        write_report(f"[YouTube] Error buscando tráiler para {movie_title}: {exc}")
        return None

    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})
        video_title = clean_text(snippet.get("title", ""))

        if not video_id or not video_title:
            continue

        if trailer_matches_movie(movie_title, video_title, release_year):
            return {
                "youtubeVideoId": video_id,
                "youtubeVideoTitle": video_title,
            }

    write_report(f"[YouTube] No se encontró tráiler confiable para {movie_title}")

    return None


def yaml_string(value: str) -> str:
    value = str(value or "")
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    value = value.replace("\n", " ").strip()

    return f'"{value}"'


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"

    return "[" + ", ".join(yaml_string(value) for value in values) + "]"


def write_markdown(article: dict, candidate: dict, group: dict) -> Path:
    target_collection = group.get(
        "targetCollection",
        candidate.get("targetCollection", "blog"),
    )

    collection_dir = CONTENT_DIR / target_collection
    collection_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    pub_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    slug_base = slugify(article["title"])
    slug = f"{slug_base}-{now.strftime('%Y-%m-%d')}-{url_hash(candidate.get('url', ''))[:6]}"
    path = collection_dir / f"{slug}.md"

    image = candidate.get("image", "")
    category = group.get("category", candidate.get("category", "Entretenimiento"))
    source_name = candidate.get("sourceName") or group.get("sourceName", "")
    source_url = candidate.get("url", "")
    author = "TELELATINO"

    frontmatter_lines = [
        "---",
        f"title: {yaml_string(article['title'])}",
        f"description: {yaml_string(article['description'])}",
        f"pubDate: {yaml_string(pub_date)}",
        f"category: {yaml_string(category)}",
        f"author: {yaml_string(author)}",
        f"tags: {yaml_list(article.get('tags', []))}",
        "draft: false",
        f"sourceName: {yaml_string(source_name)}",
        f"sourceUrl: {yaml_string(source_url)}",
    ]

    if image:
        frontmatter_lines.append(f"image: {yaml_string(image)}")
        frontmatter_lines.append(
            f"imageAlt: {yaml_string(article.get('imageAlt', article['title']))}"
        )

    if article.get("youtubeVideoId"):
        frontmatter_lines.append(
            f"youtubeVideoId: {yaml_string(article['youtubeVideoId'])}"
        )
        frontmatter_lines.append(
            f"youtubeVideoTitle: {yaml_string(article.get('youtubeVideoTitle', 'Tráiler oficial'))}"
        )

    frontmatter_lines.append("---")

    content = (
        "\n".join(frontmatter_lines)
        + "\n\n"
        + article["body"].strip()
        + "\n"
    )

    path.write_text(content, encoding="utf-8")

    write_report(f"[OK] Publicado: {path.relative_to(ROOT)}")

    return path


def get_processed_set(data) -> set[str]:
    if isinstance(data, list):
        return {str(item) for item in data}

    if isinstance(data, dict):
        values: set[str] = set()

        for key in ["urls", "hashes", "processed", "items"]:
            current = data.get(key, [])

            if isinstance(current, list):
                values.update(str(item) for item in current)

        return values

    return set()


def save_processed_set(values: set[str]) -> None:
    save_json(PROCESSED_FILE, sorted(values))


def collect_candidates(group_key: str, group: dict) -> list[dict]:
    group_type = group.get("type", "")

    if group_type == "sports_listing":
        return get_sports_candidates(group)

    if group_type == "movies_listing":
        return get_movies_candidates(group)

    write_report(f"[AVISO] Tipo de fuente no soportado para {group_key}: {group_type}")

    return []


def enrich_candidate_before_ai(candidate: dict, group: dict) -> dict | None:
    requires_trailer = bool(group.get("requiresTrailer", False))
    target_collection = group.get("targetCollection", "")
    category = normalize_text(group.get("category", ""))
    is_movie = target_collection == "blog" or category == "peliculas"

    if requires_trailer and is_movie:
        trailer = search_youtube_trailer(
            candidate.get("title", ""),
            candidate.get("releaseYear"),
        )

        if not trailer:
            write_report(
                f"[movies] Saltado porque no tiene tráiler confiable: "
                f"{candidate.get('title', '')}"
            )
            return None

        candidate = dict(candidate)
        candidate.update(trailer)

    return candidate


def title_similarity_key(title: str) -> set[str]:
    words = meaningful_words(title)
    return {word for word in words if len(word) >= 4}


def is_duplicate_by_existing_posts(candidate: dict, group: dict) -> bool:
    target_collection = group.get("targetCollection", candidate.get("targetCollection", "blog"))
    collection_dir = CONTENT_DIR / target_collection

    if not collection_dir.exists():
        return False

    candidate_words = title_similarity_key(candidate.get("title", ""))

    if not candidate_words:
        return False

    for path in list(collection_dir.glob("*.md")) + list(collection_dir.glob("*.mdx")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        existing_title = extract_frontmatter_value(text, "title")
        existing_words = title_similarity_key(existing_title)

        if not existing_words:
            continue

        overlap = len(candidate_words & existing_words)
        base = min(len(candidate_words), len(existing_words))

        if base > 0 and overlap / base >= 0.60:
            write_report(
                f"[duplicado] Saltado por tema parecido: "
                f"{candidate.get('title', '')} ~= {existing_title}"
            )
            return True

    return False


def make_candidate_processed_keys(candidate: dict, group: dict) -> list[str]:
    target_collection = group.get("targetCollection", "")
    category = normalize_text(group.get("category", ""))

    url = candidate.get("url", "")
    title = candidate.get("title", "")

    keys = [
        url_hash(url),
        url,
    ]

    if target_collection == "blog" or category == "peliculas":
        keys.append("movie-title:" + slugify(title))
        words = sorted(title_similarity_key(title))
        if words:
            keys.append("movie-words:" + "-".join(words[:8]))

    return [key for key in keys if key]


def run_group(group_key: str, group: dict, processed: set[str]) -> int:
    if not group.get("enabled", False):
        write_report(f"[{group_key}] Fuente desactivada.")
        return 0

    limit = get_dynamic_daily_limit(group)

    if limit <= 0:
        write_report(f"[{group_key}] Límite diario en 0. No se publica nada.")
        return 0

    candidates = collect_candidates(group_key, group)

    write_report(
        f"[{group_key}] Candidatos encontrados: {len(candidates)} | Límite: {limit}"
    )

    published = 0

    for candidate in candidates:
        if published >= limit:
            break

        candidate_keys = make_candidate_processed_keys(candidate, group)

        if any(key in processed for key in candidate_keys):
            continue

        if is_duplicate_by_existing_posts(candidate, group):
            processed.update(candidate_keys)
            save_processed_set(processed)
            continue

        if is_blocked_topic(
            f"{candidate.get('title', '')} {candidate.get('text', '')[:900]}"
        ):
            write_report(
                f"[{group_key}] Saltado por tema bloqueado: {candidate.get('title', '')}"
            )
            processed.update(candidate_keys)
            save_processed_set(processed)
            continue

        enriched_candidate = enrich_candidate_before_ai(candidate, group)

        if enriched_candidate is None:
            processed.update(candidate_keys)
            save_processed_set(processed)
            continue

        try:
            article = generate_with_ai_router(enriched_candidate, group)

            if enriched_candidate.get("youtubeVideoId"):
                article["youtubeVideoId"] = enriched_candidate.get("youtubeVideoId")
                article["youtubeVideoTitle"] = enriched_candidate.get("youtubeVideoTitle")

            write_markdown(article, enriched_candidate, group)

            processed.update(candidate_keys)
            save_processed_set(processed)

            published += 1
        except Exception as exc:
            write_report(
                f"[{group_key}] Error generando artículo "
                f"{candidate.get('title', '')}: {exc}"
            )
            continue

    write_report(f"[{group_key}] Publicados: {published}")

    return published


def handle_movies(group: dict, processed) -> int:
    processed_set = get_processed_set(processed)
    total = run_group("movies", group, processed_set)
    save_processed_set(processed_set)
    return total


def handle_sports(group: dict, processed) -> int:
    processed_set = get_processed_set(processed)
    total = run_group("sports", group, processed_set)
    save_processed_set(processed_set)
    return total


def main() -> int:
    reset_report()

    write_report("=== TELELATINO Auto News ===")
    write_report(f"Fecha UTC: {datetime.now(timezone.utc).isoformat()}")

    ensure_dirs()

    sources = load_json(SOURCES_FILE, {})
    processed_data = load_json(PROCESSED_FILE, [])
    processed = get_processed_set(processed_data)

    if not sources:
        write_report("[ERROR] No se encontró configuración en scripts/sources.json")
        return 1

    total_published = 0

    for group_key, group in sources.items():
        try:
            total_published += run_group(group_key, group, processed)
        except Exception as exc:
            write_report(f"[ERROR] Falló grupo {group_key}: {exc}")

    save_processed_set(processed)

    write_report(f"Total publicados: {total_published}")
    write_report("=== Fin ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
