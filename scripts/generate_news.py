import json
import os
import re
import time
import hashlib
import unicodedata
from datetime import datetime, timezone
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
REPORT_FILE = REPORTS_DIR / "auto_news_report.txt"

BLOG_DIR = ROOT / "src" / "content" / "blog"
NEWS_DIR = ROOT / "src" / "content" / "noticias"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

BLOCKED_TOPICS = [
    "agresión sexual",
    "agresion sexual",
    "abuso sexual",
    "violación",
    "violacion",
    "cárcel",
    "carcel",
    "prisión",
    "prision",
    "condenado",
    "condenada",
    "condena",
    "delito",
    "violencia",
    "asesinato",
    "muerte",
    "fallece",
    "falleció",
    "fallecio",
    "accidente mortal",
    "denuncia",
    "juicio",
    "tribunal",
    "acusado",
    "acusada",
    "cromos",
    "apuestas",
    "ganar dinero",
]

SPORT_ALLOWED_PATHS = [
    "/futbol",
]

MOVIE_ALLOWED_PATHS = [
    "/peliculas/pelicula-",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def write_report(message: str) -> None:
    ensure_reports_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {message}"
    print(line)
    with REPORT_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def reset_report() -> None:
    ensure_reports_dir()
    REPORT_FILE.write_text("", encoding="utf-8")


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as error:
        write_report(f"[WARN] No se pudo leer JSON {path}: {error}")
        return fallback


def save_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clean_text(value: str) -> str:
    if not value:
        return ""

    text = str(value)

    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")

    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )


def normalize_text(value: str) -> str:
    return strip_accents(clean_text(value).lower())


def slugify(value: str) -> str:
    value = strip_accents(value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "articulo"


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def request_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def is_quota_error(error: Exception) -> bool:
    text = str(error).lower()

    quota_fragments = [
        "429",
        "resource_exhausted",
        "rate limit",
        "rate_limit",
        "quota",
        "too many requests",
        "requests per",
        "insufficient_quota",
        "exceeded your current quota",
    ]

    return any(fragment in text for fragment in quota_fragments)


def is_blocked_topic(candidate: dict, extra_text: str = "") -> bool:
    text = f"{candidate.get('title', '')} {candidate.get('summary', '')} {extra_text}"
    text = normalize_text(text)

    for blocked in BLOCKED_TOPICS:
        if normalize_text(blocked) in text:
            return True

    return False


def should_skip_paragraph(text: str) -> bool:
    lowered = normalize_text(text)

    bad_fragments = [
        "cookies",
        "newsletter",
        "publicidad",
        "registrate",
        "suscribete",
        "siguenos",
        "sigue leyendo",
        "te recomendamos",
        "haz clic",
        "copyright",
        "todos los derechos",
        "configuracion de privacidad",
    ]

    return any(fragment in lowered for fragment in bad_fragments)


def extract_meta_image(soup: BeautifulSoup, page_url: str) -> tuple[str, str]:
    selectors = [
        ("property", "og:image"),
        ("property", "og:image:secure_url"),
        ("name", "twitter:image"),
        ("name", "twitter:image:src"),
    ]

    for attr, value in selectors:
        tag = soup.find("meta", attrs={attr: value})

        if tag and tag.get("content"):
            image_url = urljoin(page_url, clean_text(tag.get("content")))
            image_alt = ""

            alt_tag = soup.find("meta", attrs={"property": "og:image:alt"})
            if alt_tag and alt_tag.get("content"):
                image_alt = clean_text(alt_tag.get("content"))

            return image_url, image_alt

    image = soup.select_one("article img, main img, img")

    if image and image.get("src"):
        image_url = urljoin(page_url, clean_text(image.get("src")))
        image_alt = clean_text(image.get("alt", ""))
        return image_url, image_alt

    return "", ""


def extract_article_data(url: str) -> dict:
    try:
        html = request_text(url)
    except Exception as error:
        write_report(f"[ERROR] No se pudo leer artículo: {url} | {error}")
        return {
            "text": "",
            "image": "",
            "imageAlt": "",
        }

    soup = BeautifulSoup(html, "html.parser")
    image, image_alt = extract_meta_image(soup, url)

    for tag in soup(["script", "style", "noscript", "iframe", "svg", "form"]):
        tag.decompose()

    paragraphs = []

    article = soup.find("article")
    if article:
        paragraphs.extend(
            paragraph.get_text(" ", strip=True)
            for paragraph in article.find_all("p")
        )

    if not paragraphs:
        main = soup.find("main")
        if main:
            paragraphs.extend(
                paragraph.get_text(" ", strip=True)
                for paragraph in main.find_all("p")
            )

    if not paragraphs:
        paragraphs.extend(
            paragraph.get_text(" ", strip=True)
            for paragraph in soup.find_all("p")
        )

    cleaned = []

    for paragraph in paragraphs:
        paragraph = clean_text(paragraph)

        if len(paragraph) < 45:
            continue

        if should_skip_paragraph(paragraph):
            continue

        cleaned.append(paragraph)

    text = "\n\n".join(cleaned)

    return {
        "text": text[:5000],
        "image": image,
        "imageAlt": image_alt,
    }


def get_sports_candidates(url: str, source_name: str, category: str) -> list[dict]:
    try:
        html = request_text(url)
    except Exception as error:
        write_report(f"[ERROR] No se pudo leer listado deportivo: {url} | {error}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen = set()

    selectors = [
        "article h1 a",
        "article h2 a",
        "article h3 a",
        "h1 a",
        "h2 a",
        "h3 a",
        "article a",
    ]

    links = []

    for selector in selectors:
        links.extend(soup.select(selector))

    for link in links:
        title = clean_text(link.get_text(" ", strip=True))
        href = link.get("href")

        if not title or not href:
            continue

        full_url = urljoin(url, href)
        parsed = urlparse(full_url)

        if "mundodeportivo.com" not in parsed.netloc:
            continue

        if not any(path in parsed.path for path in SPORT_ALLOWED_PATHS):
            continue

        if len(title) < 35:
            continue

        if full_url in seen:
            continue

        seen.add(full_url)

        candidate = {
            "title": title,
            "url": full_url,
            "summary": "",
            "sourceName": source_name,
            "category": category,
            "image": "",
            "imageAlt": title,
        }

        if is_blocked_topic(candidate):
            write_report(f"[SKIP] Deporte bloqueado por tema delicado: {title}")
            continue

        candidates.append(candidate)

    write_report(f"[INFO] Candidatos fútbol encontrados en {source_name}: {len(candidates)}")

    return candidates


def get_movies_candidates(url: str, source_name: str, category: str) -> list[dict]:
    try:
        html = request_text(url)
    except Exception as error:
        write_report(f"[ERROR] No se pudo leer listado de películas: {url} | {error}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen = set()

    selectors = [
        "a.meta-title-link",
        "h2 a",
        "h3 a",
        ".meta-title a",
        ".card h2 a",
        ".card a",
        "article a",
        "a",
    ]

    links = []

    for selector in selectors:
        links.extend(soup.select(selector))

    for link in links:
        title = clean_text(link.get_text(" ", strip=True))
        href = link.get("href")

        if not title or not href:
            continue

        full_url = urljoin(url, href)
        parsed = urlparse(full_url)

        if "sensacine.com" not in parsed.netloc:
            continue

        if not any(path in parsed.path for path in MOVIE_ALLOWED_PATHS):
            continue

        if len(title) < 2 or len(title) > 95:
            continue

        if full_url in seen:
            continue

        seen.add(full_url)

        candidate = {
            "title": title,
            "url": full_url,
            "summary": "",
            "sourceName": source_name,
            "category": category,
            "image": "",
            "imageAlt": title,
        }

        if is_blocked_topic(candidate):
            write_report(f"[SKIP] Película bloqueada por tema delicado: {title}")
            continue

        candidates.append(candidate)

    write_report(f"[INFO] Candidatos de películas encontrados en {source_name}: {len(candidates)}")

    return candidates


def count_existing_movie_posts() -> int:
    if not BLOG_DIR.exists():
        return 0

    total = 0

    for path in BLOG_DIR.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        normalized = normalize_text(text)

        is_movie = 'category: "peliculas"' in normalized
        has_source = 'sourcename: "sensacine"' in normalized
        has_trailer = "youtubevideoid:" in normalized
        has_image = "image:" in normalized

        if is_movie and has_source and has_trailer and has_image:
            total += 1

    return total


def get_dynamic_daily_limit(name: str, config: dict) -> int:
    if name != "movies":
        return int(config.get("dailyLimit", 1))

    current_movies = count_existing_movie_posts()
    initial_target = int(config.get("initialTarget", 10))
    after_initial = int(config.get("dailyLimitAfterInitial", 1))

    if current_movies < initial_target:
        needed = initial_target - current_movies
        write_report(
            f"[INFO] Películas actuales con imagen y tráiler: {current_movies}. "
            f"Faltan {needed} para llegar a {initial_target}."
        )
        return needed

    write_report(
        f"[INFO] Ya hay {current_movies} películas con imagen y tráiler. "
        f"Se intentará publicar máximo {after_initial} nueva."
    )

    return after_initial


def build_prompt(candidate: dict, source_text: str, content_type: str) -> str:
    app_context = """
TELELATINO es una app de entretenimiento para Android con canales en vivo,
eventos deportivos, películas y estrenos. Tiene 7 días de prueba gratis al
registrarse y plan VIP de 6 meses por 6 USD.
"""

    base_rules = """
Reglas:
- No copies frases literales de la fuente.
- No publiques el artículo como exclusiva propia.
- No agregues CTA de descarga, la web ya lo inserta automáticamente.
- No uses H1.
- Usa subtítulos H2.
- Escribe entre 450 y 750 palabras.
- No inventes datos concretos si no aparecen en la fuente.
- Responde SOLO JSON válido.
"""

    if content_type == "movies":
        type_instructions = """
Tipo de artículo: película de estreno, cartelera o próximo estreno.

Objetivo:
Crear un artículo de película, no de series ni de noticias generales.
Debe incluir:
- Introducción breve.
- Sinopsis reescrita.
- De qué trata la película.
- Por qué puede llamar la atención.
- Qué público puede disfrutarla.
- Cierre informativo.

Obligatorio:
- is_specific_movie debe ser true.
- main_movie_title debe ser el nombre exacto de la película.
- youtube_search_query debe buscar el tráiler oficial de esa película.
"""
    else:
        type_instructions = """
Tipo de artículo: fútbol reciente.

Objetivo:
Crear una noticia deportiva sobre fútbol, jugadores, clubes, selecciones,
torneos, partidos o actualidad futbolística.
"""

    return f"""
Eres redactor SEO para la web TELELATINO.

Contexto:
{app_context}

Fuente:
Nombre: {candidate["sourceName"]}
URL: {candidate["url"]}
Título original: {candidate["title"]}

Texto de apoyo:
{source_text[:3200]}

{type_instructions}

{base_rules}

Formato JSON exacto:
{{
  "title": "Título SEO propio",
  "description": "Meta descripción máximo 155 caracteres",
  "body": "Contenido en Markdown, sin H1",
  "tags": ["tag1", "tag2", "tag3"],
  "is_specific_movie": false,
  "main_movie_title": "",
  "youtube_search_query": ""
}}
"""


def parse_json_response(text: str) -> dict:
    text = (text or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_article_data(data: dict, content_type: str) -> dict:
    for key in ["title", "description", "body"]:
        if key not in data or not clean_text(str(data.get(key, ""))):
            raise ValueError(f"Respuesta de IA incompleta. Falta: {key}")

    data["title"] = clean_text(data["title"])[:120]
    data["description"] = clean_text(data["description"])[:165]
    data["body"] = str(data["body"]).strip()

    tags = data.get("tags", [])

    if not isinstance(tags, list):
        tags = []

    data["tags"] = [
        clean_text(str(tag)).lower()
        for tag in tags
        if clean_text(str(tag))
    ][:6]

    if not data["tags"]:
        if content_type == "movies":
            data["tags"] = ["películas", "estrenos", "cartelera"]
        else:
            data["tags"] = ["deportes", "fútbol", "noticias"]

    data["is_specific_movie"] = bool(data.get("is_specific_movie", False))
    data["main_movie_title"] = clean_text(data.get("main_movie_title", ""))
    data["youtube_search_query"] = clean_text(data.get("youtube_search_query", ""))

    return data


def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("No existe GEMINI_API_KEY.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    return response.text or ""


def call_openai_provider(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("No existe OPENAI_API_KEY.")

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
        temperature=0.6,
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
                "content": "Eres un redactor SEO. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.6,
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
                "content": "Eres un redactor SEO. Responde únicamente JSON válido.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.6,
    )

    return response.choices[0].message.content or ""


def call_ai_provider(provider: str, prompt: str) -> str:
    if provider == "gemini":
        return call_gemini(prompt)

    if provider == "openai":
        return call_openai_provider(prompt)

    if provider == "groq":
        return call_groq(prompt)

    if provider == "mistral":
        return call_mistral(prompt)

    raise RuntimeError(f"Proveedor desconocido: {provider}")


def get_ai_provider_order(content_type: str) -> list[str]:
    if content_type == "movies":
        return ["gemini", "openai", "mistral", "groq"]

    return ["groq", "mistral", "openai", "gemini"]


def generate_with_ai_router(candidate: dict, source_text: str, content_type: str) -> dict:
    prompt = build_prompt(candidate, source_text, content_type)
    providers = get_ai_provider_order(content_type)

    last_error = None

    for provider in providers:
        try:
            write_report(f"[IA] Intentando con {provider.upper()}...")

            raw_text = call_ai_provider(provider, prompt)
            parsed = parse_json_response(raw_text)
            article = normalize_article_data(parsed, content_type)

            write_report(f"[IA OK] Artículo generado con {provider.upper()}")
            return article

        except Exception as error:
            last_error = error

            if is_quota_error(error):
                write_report(f"[IA QUOTA] {provider.upper()} sin cuota o con límite: {error}")
            else:
                write_report(f"[IA ERROR] {provider.upper()} falló: {error}")

            continue

    raise RuntimeError(f"Ningún proveedor de IA pudo generar el artículo. Último error: {last_error}")


def search_youtube_trailer(query: str) -> dict | None:
    if not YOUTUBE_API_KEY:
        write_report("[WARN] No existe YOUTUBE_API_KEY. Se publicará sin tráiler.")
        return None

    if not query:
        return None

    params = {
        "part": "snippet",
        "q": f"{query} trailer oficial español",
        "type": "video",
        "maxResults": 3,
        "videoEmbeddable": "true",
        "safeSearch": "moderate",
        "key": YOUTUBE_API_KEY,
    }

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        write_report(f"[WARN] No se pudo buscar tráiler en YouTube: {error}")
        return None

    items = data.get("items", [])

    if not items:
        write_report(f"[WARN] No se encontró tráiler para: {query}")
        return None

    for item in items:
        video_id = item.get("id", {}).get("videoId")
        title = clean_text(item.get("snippet", {}).get("title", ""))

        if not video_id:
            continue

        title_norm = normalize_text(title)

        if "trailer" in title_norm or "trailer" in normalize_text(query):
            write_report(f"[OK] Tráiler encontrado: {title}")
            return {
                "youtubeVideoId": video_id,
                "youtubeVideoTitle": title or "Tráiler oficial",
            }

    first = items[0]
    video_id = first.get("id", {}).get("videoId")
    title = clean_text(first.get("snippet", {}).get("title", ""))

    if not video_id:
        return None

    write_report(f"[OK] Video encontrado para tráiler: {title}")

    return {
        "youtubeVideoId": video_id,
        "youtubeVideoTitle": title or "Tráiler oficial",
    }


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_markdown(
    collection: str,
    article: dict,
    candidate: dict,
    article_data: dict,
    youtube_data: dict | None,
) -> Path:
    now = datetime.now(timezone.utc)
    pub_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    base_slug = slugify(article["title"])
    short_hash = url_hash(candidate["url"])[:6]

    filename = f"{base_slug}-{now.strftime('%Y-%m-%d')}-{short_hash}.md"

    target_dir = NEWS_DIR if collection == "noticias" else BLOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename

    image = article_data.get("image") or candidate.get("image")
    image_alt = article_data.get("imageAlt") or candidate.get("imageAlt") or article["title"]

    if not image:
        raise RuntimeError("No se puede publicar sin imagen destacada.")

    tags = article.get("tags") or ["telelatino"]

    frontmatter = [
        "---",
        f"title: {yaml_string(article['title'])}",
        f"description: {yaml_string(article['description'])}",
        f"pubDate: {pub_date}",
        f"category: {yaml_string(candidate['category'])}",
        'author: "TELELATINO"',
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
        "draft: false",
        f"sourceName: {yaml_string(candidate['sourceName'])}",
        f"sourceUrl: {yaml_string(candidate['url'])}",
        f"image: {yaml_string(image)}",
        f"imageAlt: {yaml_string(image_alt)}",
    ]

    if youtube_data:
        frontmatter.append(f"youtubeVideoId: {yaml_string(youtube_data['youtubeVideoId'])}")
        frontmatter.append(f"youtubeVideoTitle: {yaml_string(youtube_data['youtubeVideoTitle'])}")

    frontmatter.append("---")

    content = "\n".join(frontmatter) + "\n\n" + article["body"].strip() + "\n"

    target_path.write_text(content, encoding="utf-8")

    return target_path


def collect_candidates(name: str, config: dict) -> list[dict]:
    source_type = config.get("type")
    source_name = config.get("sourceName", name)
    category = config.get("category", "General")

    all_candidates = []

    for url in config.get("urls", []):
        if source_type == "sports_listing":
            all_candidates.extend(get_sports_candidates(url, source_name, category))
        elif source_type == "movies_listing":
            all_candidates.extend(get_movies_candidates(url, source_name, category))
        else:
            write_report(f"[WARN] Tipo de fuente desconocido: {source_type}")

    return all_candidates


def run_group(name: str, config: dict, processed: dict) -> int:
    if not config.get("enabled", True):
        write_report(f"[INFO] Grupo desactivado: {name}")
        return 0

    collection = config.get("targetCollection", "blog")
    daily_limit = get_dynamic_daily_limit(name, config)

    content_type = "movies" if name == "movies" else "sports"

    candidates = collect_candidates(name, config)

    if not candidates:
        write_report(f"[WARN] No se encontraron candidatos para {name}")
        return 0

    created = 0

    for candidate in candidates:
        if created >= daily_limit:
            break

        article_key = url_hash(candidate["url"])

        if article_key in processed.get("processed", {}):
            write_report(f"[SKIP] Ya procesado: {candidate['title']}")
            continue

        if is_blocked_topic(candidate):
            write_report(f"[SKIP] Tema delicado bloqueado: {candidate['title']}")
            processed.setdefault("processed", {})[article_key] = {
                "url": candidate["url"],
                "status": "skipped_blocked_topic",
                "date": datetime.now(timezone.utc).isoformat(),
            }
            continue

        write_report(f"[INFO] Procesando: {candidate['title']}")
        write_report(f"[INFO] URL: {candidate['url']}")

        article_data = extract_article_data(candidate["url"])
        source_text = article_data.get("text", "")

        if not article_data.get("image"):
            write_report(f"[SKIP] Sin imagen destacada, no se publica: {candidate['title']}")
            continue

        if is_blocked_topic(candidate, source_text):
            write_report(f"[SKIP] Tema delicado bloqueado después de leer: {candidate['title']}")
            processed.setdefault("processed", {})[article_key] = {
                "url": candidate["url"],
                "status": "skipped_blocked_topic_after_read",
                "date": datetime.now(timezone.utc).isoformat(),
            }
            continue

        if not source_text and not candidate.get("summary"):
            write_report("[SKIP] No hay texto suficiente para generar artículo.")
            continue

        youtube_data = None

        if content_type == "movies":
            youtube_data = search_youtube_trailer(candidate["title"])

            if config.get("requiresTrailer", True) and not youtube_data:
                write_report(f"[SKIP] Sin tráiler, no se publica la película: {candidate['title']}")
                continue

        try:
            article = generate_with_ai_router(candidate, source_text, content_type)
        except Exception as error:
            write_report(f"[ERROR] Todas las IA fallaron: {error}")
            continue

        if content_type == "movies":
            if not article.get("is_specific_movie"):
                write_report(f"[SKIP] La IA no lo identificó como película concreta: {candidate['title']}")
                continue

            if not youtube_data:
                youtube_query = article.get("youtube_search_query") or article.get("main_movie_title")
                youtube_data = search_youtube_trailer(youtube_query)

            if config.get("requiresTrailer", True) and not youtube_data:
                write_report(f"[SKIP] Sin tráiler final, no se publica la película: {candidate['title']}")
                continue

        try:
            path = write_markdown(
                collection=collection,
                article=article,
                candidate=candidate,
                article_data=article_data,
                youtube_data=youtube_data,
            )
        except Exception as error:
            write_report(f"[ERROR] No se pudo escribir Markdown: {error}")
            continue

        processed.setdefault("processed", {})[article_key] = {
            "url": candidate["url"],
            "sourceTitle": candidate["title"],
            "generatedTitle": article["title"],
            "generatedFile": str(path.relative_to(ROOT)),
            "image": article_data.get("image"),
            "hasTrailer": bool(youtube_data),
            "date": datetime.now(timezone.utc).isoformat(),
        }

        created += 1

        write_report(f"[OK] Artículo creado: {path.relative_to(ROOT)}")

    return created


def main() -> int:
    reset_report()
    write_report(">>> INICIANDO GENERADOR AUTOMÁTICO DE NOTICIAS TELELATINO <<<")

    sources = load_json(SOURCES_PATH, {})
    processed = load_json(PROCESSED_PATH, {"processed": {}})

    if not sources:
        write_report("[ERROR] No hay fuentes configuradas en scripts/sources.json")
        return 1

    total_created = 0

    for name, config in sources.items():
        write_report(f"--- Procesando grupo: {name} ---")
        created = run_group(name, config, processed)
        total_created += created
        write_report(f"[INFO] Grupo {name}: {created} artículos creados")

    save_json(PROCESSED_PATH, processed)

    write_report(f">>> PROCESO FINALIZADO. ARTÍCULOS CREADOS: {total_created} <<<")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())