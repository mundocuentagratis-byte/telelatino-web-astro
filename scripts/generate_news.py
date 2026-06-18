import json
import os
import re
import hashlib
import unicodedata
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from google import genai
from openai import OpenAI
from mistralai import Mistral


ROOT = Path(__file__).resolve().parents[1]

SOURCES_PATH = ROOT / "scripts" / "sources.json"
PROCESSED_PATH = ROOT / "scripts" / "processed_articles.json"
REPORTS_DIR = ROOT / "scripts" / "reports"
REPORT_PATH = REPORTS_DIR / "auto_news_report.txt"

CONTENT_DIR = ROOT / "src" / "content"
BLOG_DIR = CONTENT_DIR / "blog"
NEWS_DIR = CONTENT_DIR / "noticias"

SITE_NAME = "TELELATINO"
AUTHOR = "TELELATINO"

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

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BLOCKED_TOPICS = [
    "agresión sexual",
    "agresion sexual",
    "abuso sexual",
    "violación",
    "violacion",
    "condenado",
    "condena",
    "cárcel",
    "carcel",
    "prisión",
    "prision",
    "muerte",
    "muere",
    "fallece",
    "asesinato",
    "asesinado",
    "apuestas",
    "casino",
    "cromos",
    "lotería",
    "loteria",
    "onlyfans",
]

MOVIE_BAD_TITLE_WORDS = [
    "cartelera y entradas",
    "cartelera",
    "entradas",
    "sesiones",
    "horarios",
    "cines",
    "tráiler",
    "trailer",
    "vídeo",
    "video",
    "videos",
    "críticas",
    "criticas",
    "fotos",
    "noticias",
    "streaming",
    "reparto completo",
    "taquilla",
]

SPORTS_ALLOWED_DOMAINS = [
    "mundodeportivo.com",
]

MOVIE_ALLOWED_DOMAINS = [
    "sensacine.com",
    "espinof.com",
    "decine21.com",
]

MOVIE_2026_HINTS = [
    "2026",
    "estreno 2026",
    "película 2026",
    "pelicula 2026",
    "cine 2026",
    "próximamente",
    "proximamente",
    "estrenos",
]

SPORTS_STYLE_OPENERS = [
    "El fútbol vuelve a dejar una noticia con lectura clara para los aficionados.",
    "La actualidad deportiva se mueve rápido y este tema ya empieza a generar conversación.",
    "En una semana cargada de fútbol, esta noticia suma un nuevo detalle al panorama deportivo.",
    "No todas las noticias deportivas pesan igual, pero algunas ayudan a entender el momento de un equipo.",
    "La jornada deja un movimiento interesante dentro del fútbol y vale la pena mirarlo con calma.",
]

MOVIE_STYLE_OPENERS = [
    "El calendario de cine sigue tomando forma y esta película empieza a ganar espacio entre los estrenos a seguir.",
    "Cada temporada trae títulos que despiertan curiosidad antes de llegar a salas o plataformas.",
    "Entre los próximos estrenos, esta película aparece como una de esas propuestas que vale la pena tener en el radar.",
    "El cine de 2026 empieza a perfilar varios títulos llamativos, y este es uno de ellos.",
    "Hay películas que llaman la atención no solo por su reparto o su historia, sino por la expectativa que generan antes del estreno.",
]


def ensure_dirs() -> None:
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def reset_report() -> None:
    ensure_dirs()
    REPORT_PATH.write_text("", encoding="utf-8")


def log(message: str) -> None:
    print(message)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def write_report(message: str) -> None:
    log(message)


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = str(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def strip_accents(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

    return text


def normalize_text(text: str) -> str:
    text = clean_text(text).lower()
    text = strip_accents(text)

    return text


def slugify(text: str, max_length: int = 82) -> str:
    text = normalize_text(text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")

    if not text:
        text = "telelatino-articulo"

    return text[:max_length].strip("-")


def url_hash(url: str, length: int = 8) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:length]


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def request_text(url: str, timeout: int = 25) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()

    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "ascii"}:
        response.encoding = response.apparent_encoding or "utf-8"

    return response.text


def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def same_or_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    domain = get_domain(url)
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in allowed_domains)


def extract_meta(soup: BeautifulSoup, name: str) -> str:
    selectors = [
        ("property", name),
        ("name", name),
    ]

    for attr, value in selectors:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return clean_text(tag["content"])

    return ""


def extract_meta_title(soup: BeautifulSoup) -> str:
    title = extract_meta(soup, "og:title")
    if title:
        return title

    if soup.title and soup.title.string:
        return clean_text(soup.title.string)

    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" ", strip=True))

    return ""


def extract_meta_description(soup: BeautifulSoup) -> str:
    description = extract_meta(soup, "description")
    if description:
        return description

    description = extract_meta(soup, "og:description")
    if description:
        return description

    paragraphs = [
        clean_text(p.get_text(" ", strip=True))
        for p in soup.find_all("p")
    ]
    paragraphs = [p for p in paragraphs if len(p) > 80]

    return paragraphs[0] if paragraphs else ""


def extract_meta_image(soup: BeautifulSoup, base_url: str) -> str:
    candidates = [
        extract_meta(soup, "og:image"),
        extract_meta(soup, "twitter:image"),
    ]

    for item in soup.find_all(["img", "source"]):
        src = (
            item.get("src")
            or item.get("data-src")
            or item.get("data-original")
            or item.get("data-lazy-src")
            or item.get("srcset")
        )

        if not src:
            continue

        src = str(src).split(",")[0].strip().split(" ")[0]

        if src and not src.startswith("data:"):
            candidates.append(src)

    for image in candidates:
        if not image:
            continue

        image = image.strip()

        if image.startswith("//"):
            image = "https:" + image

        image = urljoin(base_url, image)

        lowered = image.lower()

        if not image.startswith("http"):
            continue

        if any(bad in lowered for bad in ["logo", "icon", "avatar", "sprite"]):
            continue

        return image

    return ""


def should_skip_paragraph(text: str) -> bool:
    n = normalize_text(text)

    if len(n) < 45:
        return True

    bad_phrases = [
        "suscríbete",
        "suscribete",
        "newsletter",
        "publicidad",
        "cookies",
        "política de privacidad",
        "politica de privacidad",
        "aceptar",
        "iniciar sesión",
        "iniciar sesion",
        "regístrate",
        "registrate",
        "síguenos",
        "siguenos",
        "comparte",
        "haz clic",
        "leer también",
        "lee también",
        "también puedes leer",
        "tambien puedes leer",
        "todos los derechos reservados",
    ]

    return any(item in n for item in bad_phrases)


def extract_article_text(soup: BeautifulSoup) -> str:
    for bad in soup(["script", "style", "noscript", "svg", "form", "button", "iframe"]):
        bad.decompose()

    content_blocks = []

    selectors = [
        "article",
        "main",
        ".article",
        ".article-content",
        ".news-content",
        ".entry-content",
        ".post-content",
        ".content",
    ]

    for selector in selectors:
        found = soup.select(selector)
        for block in found:
            text = block.get_text(" ", strip=True)
            if len(text) > 500:
                content_blocks.append(block)

    if content_blocks:
        block = max(content_blocks, key=lambda b: len(b.get_text(" ", strip=True)))
        paragraphs = [
            clean_text(p.get_text(" ", strip=True))
            for p in block.find_all(["p", "li"])
        ]
    else:
        paragraphs = [
            clean_text(p.get_text(" ", strip=True))
            for p in soup.find_all(["p", "li"])
        ]

    paragraphs = [p for p in paragraphs if not should_skip_paragraph(p)]

    if not paragraphs:
        text = soup.get_text(" ", strip=True)
        text = clean_text(text)

        return text[:3500]

    text = "\n\n".join(paragraphs)

    return text[:7000]


def is_blocked_topic(title: str, description: str = "", body: str = "") -> bool:
    combined = normalize_text(f"{title} {description} {body}")

    return any(normalize_text(item) in combined for item in BLOCKED_TOPICS)


def extract_date_from_url(url: str):
    patterns = [
        r"/(20\d{2})/(\d{2})/(\d{2})/",
        r"-(20\d{2})-(\d{2})-(\d{2})",
        r"/(20\d{2})(\d{2})(\d{2})/",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)

        if not match:
            continue

        try:
            year, month, day = map(int, match.groups())
            return date(year, month, day)
        except Exception:
            continue

    return None


def is_recent_url(url: str, max_age_days: int) -> bool:
    found_date = extract_date_from_url(url)

    if not found_date:
        return True

    age = (today_utc() - found_date).days

    return -2 <= age <= max_age_days


def get_source_name_from_url(url: str, default_name: str) -> str:
    domain = get_domain(url)

    if "mundodeportivo" in domain:
        return "Mundo Deportivo"

    if "sensacine" in domain:
        return "SensaCine"

    if "espinof" in domain:
        return "Espinof"

    if "decine21" in domain:
        return "Decine21"

    return default_name


def extract_links_from_listing(url: str) -> list[dict]:
    html = request_text(url)
    soup = BeautifulSoup(html, "html.parser")

    candidates = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")

        if not href:
            continue

        full_url = urljoin(url, href)
        full_url = full_url.split("#")[0].strip()

        if not full_url.startswith("http"):
            continue

        if full_url in seen:
            continue

        seen.add(full_url)

        title = clean_text(a.get_text(" ", strip=True))

        if not title:
            title = clean_text(a.get("title", "") or a.get("aria-label", ""))

        image = ""
        img = a.find("img")

        if img:
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
            )

            if src:
                image = urljoin(url, src)

        parent = a.parent

        for _ in range(3):
            if parent and not image:
                img = parent.find("img") if hasattr(parent, "find") else None

                if img:
                    src = (
                        img.get("src")
                        or img.get("data-src")
                        or img.get("data-original")
                        or img.get("data-lazy-src")
                    )

                    if src:
                        image = urljoin(url, src)

            parent = parent.parent if parent else None

        candidates.append(
            {
                "url": full_url,
                "title": title,
                "image": image,
                "listing": url,
            }
        )

    return candidates


def is_sports_candidate_url(url: str) -> bool:
    if not same_or_allowed_domain(url, SPORTS_ALLOWED_DOMAINS):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()

    if any(x in path for x in ["/videos/", "/video/", "/album/", "/fotos/", "/directo/"]):
        return False

    allowed_paths = [
        "/futbol",
        "/loultimo",
        "/mundial",
        "/fc-barcelona",
        "/real-madrid",
        "/atletico-madrid",
        "/premier-league",
        "/fichajes",
        "/femenino",
    ]

    if not any(item in path for item in allowed_paths):
        return False

    if path.count("/") < 2:
        return False

    return True


def is_movie_candidate_url(url: str) -> bool:
    if not same_or_allowed_domain(url, MOVIE_ALLOWED_DOMAINS):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()
    domain = get_domain(url)

    blocked_paths = [
        "/videos/",
        "/video/",
        "/trailer/",
        "/trailers/",
        "/criticas/",
        "/critica/",
        "/fotos/",
        "/noticias/",
        "/streaming/",
        "/series/",
        "/tv/",
        "/cartelera/",
        "/sesiones/",
        "/bandas-sonoras/",
    ]

    if any(item in path for item in blocked_paths):
        return False

    if "sensacine.com" in domain:
        return "/peliculas/pelicula-" in path

    if "espinof.com" in domain:
        if "/categoria/" in path:
            return False

        return len(path.strip("/").split("/")) >= 1

    if "decine21.com" in domain:
        if "/estrenos/cine" in path:
            return False

        if any(x in path for x in ["/peliculas/", "/estrenos/", "/cine/"]):
            return True

        return len(path.strip("/").split("/")) >= 1

    return False


def movie_title_is_invalid(title: str) -> bool:
    n = normalize_text(title)

    if not n or len(n) < 4:
        return True

    if any(bad in n for bad in MOVIE_BAD_TITLE_WORDS):
        return True

    invalid_exact = {
        "peliculas",
        "películas",
        "estrenos",
        "cine",
        "sensa cine",
        "sensacine",
        "espinof",
        "decine21",
    }

    if n in invalid_exact:
        return True

    return False


def extract_movie_release_year(title: str, description: str, body: str, url: str = ""):
    combined = f"{title}\n{description}\n{body}\n{url}"

    patterns = [
        r"(?:estreno|estrena|lanzamiento|llega|programada|prevista|previsto|película|pelicula)[^\n\.]{0,100}\b(20\d{2})\b",
        r"\b(20\d{2})\b",
    ]

    years = []

    for pattern in patterns:
        for match in re.finditer(pattern, combined, flags=re.I):
            try:
                years.append(int(match.group(1)))
            except Exception:
                pass

    if not years:
        return None

    future_years = [year for year in years if 2025 <= year <= 2035]

    if not future_years:
        return None

    if 2026 in future_years:
        return 2026

    return min(future_years)


def parse_frontmatter_value(text: str, key: str) -> str:
    pattern = rf"^{re.escape(key)}:\s*(.+)$"
    match = re.search(pattern, text, flags=re.M)

    if not match:
        return ""

    value = match.group(1).strip()
    value = value.strip('"').strip("'")

    return value


def existing_posts(collection_dir: Path) -> list[dict]:
    posts = []

    if not collection_dir.exists():
        return posts

    for path in collection_dir.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        posts.append(
            {
                "path": path,
                "title": parse_frontmatter_value(text, "title"),
                "category": parse_frontmatter_value(text, "category"),
                "pubDate": parse_frontmatter_value(text, "pubDate"),
                "sourceUrl": parse_frontmatter_value(text, "sourceUrl"),
                "image": parse_frontmatter_value(text, "image"),
                "youtubeVideoId": parse_frontmatter_value(text, "youtubeVideoId"),
            }
        )

    return posts


def count_existing_movies() -> int:
    posts = existing_posts(BLOG_DIR)
    total = 0

    for post in posts:
        category = normalize_text(post.get("category", ""))

        if "pelicula" in category:
            total += 1

    return total


def count_existing_sports_news() -> int:
    posts = existing_posts(NEWS_DIR)
    total = 0

    for post in posts:
        category = normalize_text(post.get("category", ""))

        if "deporte" in category or "futbol" in category:
            total += 1

    return total


def count_today_posts(collection_dir: Path) -> int:
    posts = existing_posts(collection_dir)
    today_str = today_utc().isoformat()
    total = 0

    for post in posts:
        pub = post.get("pubDate", "")

        if pub.startswith(today_str):
            total += 1

    return total


def existing_source_urls() -> set[str]:
    urls = set()

    for collection in [BLOG_DIR, NEWS_DIR]:
        for post in existing_posts(collection):
            url = post.get("sourceUrl", "")

            if url:
                urls.add(url)

    return urls


def should_skip_existing_title(title: str, collection_dir: Path) -> bool:
    target = normalize_text(title)

    if not target:
        return False

    for post in existing_posts(collection_dir):
        current = normalize_text(post.get("title", ""))

        if not current:
            continue

        if current == target:
            return True

        if target[:70] and target[:70] in current:
            return True

        if current[:70] and current[:70] in target:
            return True

    return False


def get_dynamic_limit(group_name: str, group: dict) -> int:
    if group_name == "movies":
        current = count_existing_movies()
        initial_target = int(group.get("initialTarget", 10))
        after_initial = int(group.get("dailyLimitAfterInitial", 1))

        if current < initial_target:
            return max(initial_target - current, 0)

        return after_initial

    if group_name == "sports":
        current = count_existing_sports_news()
        initial_target = int(group.get("initialTarget", 10))
        daily_limit = int(group.get("dailyLimit", 2))
        daily_limit_per_day = int(group.get("dailyLimitPerDay", 6))
        today_count = count_today_posts(NEWS_DIR)

        if current < initial_target:
            return max(initial_target - current, 0)

        remaining_today = max(daily_limit_per_day - today_count, 0)

        return min(daily_limit, remaining_today)

    return int(group.get("dailyLimit", 1))


def meaningful_words(text: str) -> list[str]:
    n = normalize_text(text)
    words = re.findall(r"[a-z0-9]+", n)

    stop = {
        "de",
        "la",
        "el",
        "los",
        "las",
        "un",
        "una",
        "y",
        "o",
        "en",
        "para",
        "con",
        "por",
        "del",
        "al",
        "que",
        "se",
        "su",
        "sus",
        "es",
        "sobre",
        "pelicula",
        "peliculas",
        "estreno",
        "trailer",
        "oficial",
        "cine",
        "noticia",
        "futbol",
        "mundial",
    }

    return [word for word in words if word not in stop and len(word) >= 3]


def trailer_matches_movie(movie_title: str, video_title: str, release_year=None) -> bool:
    movie_words = meaningful_words(movie_title)
    video = normalize_text(video_title)

    if not movie_words:
        return False

    hits = sum(1 for word in movie_words[:6] if word in video)

    if hits < max(1, min(3, len(movie_words))):
        return False

    if "trailer" not in video and "avance" not in video:
        return False

    if release_year:
        years = re.findall(r"\b20\d{2}\b", video)

        if years and str(release_year) not in years:
            return False

    return True


def search_youtube_trailer(movie_title: str, release_year=None):
    if not YOUTUBE_API_KEY:
        return None

    query = f"{movie_title} trailer oficial español {release_year or 2026}"

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 6,
        "key": YOUTUBE_API_KEY,
        "safeSearch": "moderate",
        "relevanceLanguage": "es",
    }

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        log(f"[youtube] No se pudo buscar trailer para {movie_title}: {e}")
        return None

    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})
        title = clean_text(snippet.get("title", ""))

        if not video_id or not title:
            continue

        if trailer_matches_movie(movie_title, title, release_year):
            return {
                "id": video_id,
                "title": title,
            }

    return None


def provider_available(provider: str) -> bool:
    if provider == "gemini":
        return bool(GEMINI_API_KEY)

    if provider == "groq":
        return bool(GROQ_API_KEY)

    if provider == "mistral":
        return bool(MISTRAL_API_KEY)

    if provider == "openai":
        return bool(OPENAI_API_KEY)

    if provider == "cohere":
        return bool(COHERE_API_KEY)

    return False


def rotate_list(items: list[str], seed: str) -> list[str]:
    if not items:
        return items

    index = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(items)

    return items[index:] + items[:index]


def get_ai_provider_order(article_type: str, seed: str) -> list[str]:
    if article_type == "movie":
        base = ["mistral", "cohere", "gemini", "groq", "openai"]
    else:
        base = ["groq", "mistral", "cohere", "gemini", "openai"]

    base = rotate_list(base, seed)

    return [provider for provider in base if provider_available(provider)]


def extract_json_from_text(text: str) -> dict:
    text = text.strip()

    text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text, strict=False)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate, strict=False)
        except Exception:
            pass

    raise ValueError("La IA no devolvió JSON válido.")


def normalize_article_data(data: dict, fallback_title: str, article_type: str) -> dict:
    title = clean_text(str(data.get("title", "") or fallback_title))
    description = clean_text(str(data.get("description", "")))
    intro = clean_text(str(data.get("intro", "")))
    body = str(data.get("body", "")).strip()
    tags = data.get("tags", [])

    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

    if not isinstance(tags, list):
        tags = []

    tags = [clean_text(str(tag)) for tag in tags if clean_text(str(tag))]
    tags = tags[:6]

    body = body.replace("Sinopsis reescrita", "Sinopsis")
    body = body.replace("sinopsis reescrita", "sinopsis")
    body = body.replace("Fuente consultada", "")
    body = body.replace("Fuentes consultadas", "")
    body = body.replace("Como modelo de lenguaje", "")
    body = body.replace("Como IA", "")

    if article_type == "movie":
        category = "Películas"
    else:
        category = "Deportes"

    if not description:
        description = intro[:155] if intro else title[:155]

    return {
        "title": title,
        "description": description[:180],
        "intro": intro,
        "body": body,
        "tags": tags,
        "category": category,
    }


def build_prompt(
    article_type: str,
    source_title: str,
    source_description: str,
    source_body: str,
    source_url: str,
    source_name: str,
    release_year=None,
) -> str:
    if article_type == "movie":
        opener_seed = MOVIE_STYLE_OPENERS[int(url_hash(source_url, 2), 16) % len(MOVIE_STYLE_OPENERS)]
        word_target = "700 a 950 palabras"
        article_kind = "artículo de película"
        category_notes = f"""
El artículo es para la sección Películas de TELELATINO.
La película debe tratarse como estreno o título de 2026.
Año detectado: {release_year or "2026"}.

Objetivo:
- Que se lea como una recomendación editorial natural.
- Explicar por qué puede interesar.
- Incluir una sección llamada "Sinopsis".
- No uses jamás "Sinopsis reescrita".
- No digas que la película está disponible en TELELATINO si la fuente no lo confirma.
- Puedes cerrar invitando al lector a descargar TELELATINO para descubrir entretenimiento desde Android.
"""
    else:
        opener_seed = SPORTS_STYLE_OPENERS[int(url_hash(source_url, 2), 16) % len(SPORTS_STYLE_OPENERS)]
        word_target = "650 a 900 palabras"
        article_kind = "noticia deportiva"
        category_notes = """
El artículo es para la sección Noticias de TELELATINO.
Debe sentirse actual, claro y útil para aficionados al fútbol.

Objetivo:
- Explicar qué pasó.
- Dar contexto.
- Contar por qué importa.
- Evitar sonar robótico o repetitivo.
- No inventes resultados, fichajes cerrados, lesiones o declaraciones que no estén en la fuente.
- Puedes cerrar invitando al lector a seguir noticias y entretenimiento desde TELELATINO.
"""

    return f"""
Eres el redactor principal de TELELATINO. Escribes en español neutro, profesional, humano y con personalidad.

Necesito que redactes un {article_kind} para una web pública.

Estilo obligatorio:
- Redacción natural, como un solo escritor real.
- Profesional, clara, humana y fácil de leer.
- Nada robótico, nada repetitivo, nada genérico.
- No uses frases como "en este artículo exploraremos", "sinopsis reescrita", "fuente consultada", "según la fuente consultada".
- No menciones que usas inteligencia artificial.
- No copies literalmente el texto original.
- No inventes datos.
- Evita títulos de secciones repetidos en todos los artículos.
- Usa subtítulos H2 en Markdown con personalidad, pero sin exagerar.
- Usa párrafos medianos, no bloques enormes.
- Mantén una estructura ordenada.
- Extensión aproximada: {word_target}.
- Tono: cercano, editorial y confiable.
- Incluye una llamada suave hacia TELELATINO al final, sin prometer que ese evento o película específica está disponible si no consta.

Frase de arranque sugerida para inspirar el tono, no la copies obligatoriamente:
"{opener_seed}"

{category_notes}

Devuelve únicamente JSON válido con esta estructura exacta:
{{
  "title": "Título SEO natural, sin comillas raras, máximo 70 caracteres",
  "description": "Meta descripción clara, máximo 155 caracteres",
  "intro": "Entradilla breve, atractiva y humana",
  "body": "Artículo completo en Markdown. Usa ## para subtítulos. No incluyas el H1 porque el título ya existe.",
  "tags": ["tag1", "tag2", "tag3", "tag4"]
}}

Datos de la fuente:
Fuente: {source_name}
URL: {source_url}

Título original:
{source_title}

Descripción original:
{source_description}

Texto base:
{source_body[:6000]}
""".strip()


def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("No existe GEMINI_API_KEY.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    text = getattr(response, "text", None)

    if not text:
        raise RuntimeError("Gemini no devolvió texto.")

    return text


def call_openai_provider(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("No existe OPENAI_API_KEY.")

    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Eres un redactor SEO profesional. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.55,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or ""


def call_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("No existe GROQ_API_KEY.")

    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Eres un redactor SEO profesional. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.55,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or ""


def call_mistral(prompt: str) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("No existe MISTRAL_API_KEY.")

    client = Mistral(api_key=MISTRAL_API_KEY)

    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Eres un redactor SEO profesional. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.55,
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
                "content": "Eres un redactor SEO profesional. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.55,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=80)

    if response.status_code >= 400:
        raise RuntimeError(f"Cohere error {response.status_code}: {response.text[:1000]}")

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

    raise RuntimeError("Cohere no devolvió texto válido.")


def call_ai_provider(provider: str, prompt: str) -> str:
    if provider == "gemini":
        return call_gemini(prompt)

    if provider == "groq":
        return call_groq(prompt)

    if provider == "mistral":
        return call_mistral(prompt)

    if provider == "openai":
        return call_openai_provider(prompt)

    if provider == "cohere":
        return call_cohere(prompt)

    raise RuntimeError(f"Proveedor no soportado: {provider}")


def is_quota_error(error: Exception) -> bool:
    text = normalize_text(str(error))

    patterns = [
        "quota",
        "rate limit",
        "insufficient_quota",
        "too many requests",
        "429",
        "exceeded",
    ]

    return any(pattern in text for pattern in patterns)


def generate_with_ai_router(
    article_type: str,
    prompt: str,
    fallback_title: str,
    seed: str,
) -> tuple[dict, str]:
    providers = get_ai_provider_order(article_type, seed)

    if not providers:
        raise RuntimeError("No hay proveedores IA configurados.")

    last_error = None

    for provider in providers:
        try:
            raw = call_ai_provider(provider, prompt)
            parsed = extract_json_from_text(raw)
            normalized = normalize_article_data(parsed, fallback_title, article_type)

            return normalized, provider
        except Exception as e:
            last_error = e

            if is_quota_error(e):
                log(f"[IA] {provider} sin cuota o con límite: {str(e)[:240]}")
            else:
                log(f"[IA] Falló {provider}: {str(e)[:240]}")

            continue

    raise RuntimeError(f"Ningún proveedor IA funcionó. Último error: {last_error}")


def yaml_string(value: str) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    value = value.replace("\n", " ").strip()

    return f'"{value}"'


def markdown_frontmatter(data: dict) -> str:
    lines = ["---"]

    for key, value in data.items():
        if value is None or value == "":
            continue

        if isinstance(value, list):
            lines.append(f"{key}:")

            for item in value:
                lines.append(f"  - {yaml_string(item)}")
        elif key == "pubDate":
            lines.append(f"{key}: {yaml_string(value)}")
        else:
            lines.append(f"{key}: {yaml_string(value)}")

    lines.append("---")

    return "\n".join(lines)


def clean_generated_body(body: str) -> str:
    body = body.strip()

    body = re.sub(r"^# .+\n+", "", body)
    body = body.replace("###", "##")

    body = body.replace("Sinopsis reescrita:", "Sinopsis:")
    body = body.replace("Sinopsis reescrita", "Sinopsis")
    body = body.replace("sinopsis reescrita", "sinopsis")
    body = body.replace("Fuente consultada:", "")
    body = body.replace("Fuentes consultadas:", "")
    body = body.replace("Fuente:", "")

    body = re.sub(r"\n{3,}", "\n\n", body)

    return body.strip()


def write_markdown(
    collection: str,
    article: dict,
    source_data: dict,
    source_name: str,
    source_url: str,
    image: str,
    trailer: dict | None = None,
) -> Path:
    if collection == "blog":
        target_dir = BLOG_DIR
    else:
        target_dir = NEWS_DIR

    target_dir.mkdir(parents=True, exist_ok=True)

    pub_date = now_iso()
    slug_base = slugify(article["title"])
    filename = f"{slug_base}-{today_utc().isoformat()}-{url_hash(source_url, 6)}.md"
    path = target_dir / filename

    if path.exists():
        filename = f"{slug_base}-{today_utc().isoformat()}-{url_hash(source_url, 10)}.md"
        path = target_dir / filename

    frontmatter = {
        "title": article["title"],
        "description": article["description"],
        "pubDate": pub_date,
        "category": article["category"],
        "author": AUTHOR,
        "tags": article.get("tags", []),
        "draft": False,
        "sourceName": source_name,
        "sourceUrl": source_url,
        "image": image,
        "imageAlt": article["title"],
    }

    if trailer:
        frontmatter["youtubeVideoId"] = trailer.get("id", "")
        frontmatter["youtubeVideoTitle"] = trailer.get("title", "")

    intro = article.get("intro", "").strip()
    body = clean_generated_body(article.get("body", ""))

    content_parts = [markdown_frontmatter(frontmatter), ""]

    if intro:
        content_parts.append(intro)
        content_parts.append("")

    content_parts.append(body)
    content_parts.append("")
    content_parts.append(
        "Si quieres seguir descubriendo entretenimiento, noticias deportivas y películas desde tu móvil, puedes descargar TELELATINO para Android y revisar sus opciones disponibles."
    )
    content_parts.append("")

    path.write_text("\n".join(content_parts), encoding="utf-8")

    return path


def mark_processed(processed: dict, url: str, path: Path, title: str) -> None:
    processed.setdefault("urls", [])
    processed.setdefault("items", [])

    if url not in processed["urls"]:
        processed["urls"].append(url)

    processed["items"].append(
        {
            "url": url,
            "path": str(path.relative_to(ROOT)) if isinstance(path, Path) and path.exists() else str(path),
            "title": title,
            "date": now_iso(),
        }
    )

    processed["urls"] = processed["urls"][-3000:]
    processed["items"] = processed["items"][-3000:]


def handle_sports(group: dict, processed: dict) -> int:
    if not group.get("enabled", True):
        log("[sports] Desactivado.")
        return 0

    limit = get_dynamic_limit("sports", group)

    if limit <= 0:
        log("[sports] Límite del día completado.")
        return 0

    candidates = get_sports_candidates(group, processed)
    log(f"[sports] Candidatos encontrados: {len(candidates)} | Límite: {limit}")

    published = 0
    existing_urls = existing_source_urls()

    for candidate in candidates:
        if published >= limit:
            break

        url = candidate["url"]

        if url in existing_urls:
            continue

        try:
            source_data = extract_article_data(url, candidate.get("imageHint", ""))
        except Exception as e:
            log(f"[sports] No se pudo leer artículo {url}: {e}")
            continue

        title = source_data.get("title", "") or candidate.get("titleHint", "")
        description = source_data.get("description", "")
        body = source_data.get("body", "")
        image = source_data.get("image", "")

        if not title or len(title) < 12:
            log(f"[sports] Saltado por título inválido: {url}")
            continue

        if is_blocked_topic(title, description, body):
            log(f"[sports] Saltado por tema sensible: {title}")
            mark_processed(processed, url, Path("saltado"), title)
            continue

        if group.get("requiresImage", True) and not image:
            log(f"[sports] Saltado sin imagen: {title}")
            continue

        if should_skip_existing_title(title, NEWS_DIR):
            log(f"[sports] Saltado por título duplicado: {title}")
            mark_processed(processed, url, Path("duplicado"), title)
            continue

        prompt = build_prompt(
            article_type="sports",
            source_title=title,
            source_description=description,
            source_body=body,
            source_url=url,
            source_name=candidate.get("sourceName", group.get("sourceName", "Mundo Deportivo")),
        )

        try:
            article, provider = generate_with_ai_router(
                article_type="sports",
                prompt=prompt,
                fallback_title=title,
                seed=url,
            )
            log(f"[IA] Noticia generada con {provider}: {article['title']}")
        except Exception as e:
            log(f"[sports] IA falló para {title}: {e}")
            continue

        try:
            path = write_markdown(
                collection=group.get("targetCollection", "noticias"),
                article=article,
                source_data=source_data,
                source_name=candidate.get("sourceName", group.get("sourceName", "Mundo Deportivo")),
                source_url=url,
                image=image,
                trailer=None,
            )
        except Exception as e:
            log(f"[sports] No se pudo escribir Markdown: {e}")
            continue

        mark_processed(processed, url, path, article["title"])
        existing_urls.add(url)
        published += 1

        log(f"[OK] Noticia publicada: {path.relative_to(ROOT)}")

    log(f"[sports] Publicados: {published}")

    return published


def handle_movies(group: dict, processed: dict) -> int:
    if not group.get("enabled", True):
        log("[movies] Desactivado.")
        return 0

    limit = get_dynamic_limit("movies", group)

    if limit <= 0:
        log("[movies] Límite completado.")
        return 0

    min_release_year = int(group.get("minReleaseYear", 2026))
    candidates = get_movie_candidates(group, processed)
    log(f"[movies] Candidatos encontrados: {len(candidates)} | Límite: {limit}")

    published = 0
    existing_urls = existing_source_urls()

    current_movies = count_existing_movies()
    initial_target = int(group.get("initialTarget", 10))
    filling_initial = current_movies < initial_target

    for candidate in candidates:
        if published >= limit:
            break

        url = candidate["url"]

        if url in existing_urls:
            continue

        try:
            source_data = extract_article_data(url, candidate.get("imageHint", ""))
        except Exception as e:
            log(f"[movies] No se pudo leer película {url}: {e}")
            continue

        title = source_data.get("title", "") or candidate.get("titleHint", "")
        description = source_data.get("description", "")
        body = source_data.get("body", "")
        image = source_data.get("image", "")

        if movie_title_is_invalid(title):
            log(f"[movies] Saltado por título inválido: {title}")
            continue

        release_year = extract_movie_release_year(title, description, body, url)

        if not release_year:
            log(f"[movies] Saltado sin año claro: {title}")
            continue

        if release_year < min_release_year:
            log(f"[movies] Saltado por año {release_year}: {title}")
            continue

        if release_year != 2026:
            log(f"[movies] Saltado porque no es 2026: {title} ({release_year})")
            continue

        if group.get("requiresImage", True) and not image:
            log(f"[movies] Saltado sin imagen: {title}")
            continue

        if should_skip_existing_title(title, BLOG_DIR):
            log(f"[movies] Saltado por título duplicado: {title}")
            mark_processed(processed, url, Path("duplicado"), title)
            continue

        trailer = search_youtube_trailer(title, release_year)

        if group.get("requiresTrailer", False) and not trailer and not filling_initial:
            log(f"[movies] Saltado sin trailer oficial: {title}")
            continue

        if group.get("requiresTrailer", False) and not trailer and filling_initial:
            log(f"[movies] Sin trailer, pero se permite para completar las 10 iniciales: {title}")

        prompt = build_prompt(
            article_type="movie",
            source_title=title,
            source_description=description,
            source_body=body,
            source_url=url,
            source_name=candidate.get("sourceName", group.get("sourceName", "Fuentes de cine")),
            release_year=release_year,
        )

        try:
            article, provider = generate_with_ai_router(
                article_type="movie",
                prompt=prompt,
                fallback_title=title,
                seed=url,
            )
            log(f"[IA] Película generada con {provider}: {article['title']}")
        except Exception as e:
            log(f"[movies] IA falló para {title}: {e}")
            continue

        try:
            path = write_markdown(
                collection=group.get("targetCollection", "blog"),
                article=article,
                source_data=source_data,
                source_name=candidate.get("sourceName", group.get("sourceName", "Fuentes de cine")),
                source_url=url,
                image=image,
                trailer=trailer,
            )
        except Exception as e:
            log(f"[movies] No se pudo escribir Markdown: {e}")
            continue

        mark_processed(processed, url, path, article["title"])
        existing_urls.add(url)
        published += 1

        log(f"[OK] Película publicada: {path.relative_to(ROOT)}")

    log(f"[movies] Publicados: {published}")

    return published


def main() -> int:
    ensure_dirs()
    reset_report()

    log("=== TELELATINO Auto News ===")
    log(f"Fecha UTC: {datetime.now(timezone.utc).isoformat()}")

    sources = load_json(SOURCES_PATH, {})
    processed = load_json(PROCESSED_PATH, {"urls": [], "items": []})

    if not isinstance(processed, dict):
        processed = {"urls": [], "items": []}

    processed.setdefault("urls", [])
    processed.setdefault("items", [])

    total = 0

    sports_group = sources.get("sports")

    if isinstance(sports_group, dict):
        try:
            total += handle_sports(sports_group, processed)
        except Exception as e:
            log(f"[sports] Error general: {e}")

    movies_group = sources.get("movies")

    if isinstance(movies_group, dict):
        try:
            total += handle_movies(movies_group, processed)
        except Exception as e:
            log(f"[movies] Error general: {e}")

    save_json(PROCESSED_PATH, processed)

    log(f"Total publicados: {total}")
    log("=== Fin ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())