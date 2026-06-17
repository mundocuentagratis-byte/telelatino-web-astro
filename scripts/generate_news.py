import json
import os
import re
import time
import hashlib
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from google import genai


ROOT = Path(__file__).resolve().parents[1]

SOURCES_PATH = ROOT / "scripts" / "sources.json"
PROCESSED_PATH = ROOT / "scripts" / "processed_articles.json"

REPORTS_DIR = ROOT / "scripts" / "reports"
REPORT_FILE = REPORTS_DIR / "auto_news_report.txt"

BLOG_DIR = ROOT / "src" / "content" / "blog"
NEWS_DIR = ROOT / "src" / "content" / "noticias"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

DEFAULT_IMAGE = "/images/telelatino-app.jpg"

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
    "polémica grave",
    "polemicagrave",
    "cromos",
    "apuestas",
    "ganar dinero",
]

MOVIE_ALLOWED_KEYWORDS = [
    "película",
    "pelicula",
    "cine",
    "estreno",
    "estrenos",
    "tráiler",
    "trailer",
    "cartelera",
    "sinopsis",
    "saga",
    "director",
    "actriz",
    "actor",
]

MOVIE_BLOCKED_KEYWORDS = [
    "serie",
    "series",
    "temporada",
    "capítulo",
    "capitulo",
    "programa",
    "reality",
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
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    return response.text


def is_blocked_topic(candidate: dict, extra_text: str = "") -> bool:
    text = f"{candidate.get('title', '')} {candidate.get('summary', '')} {extra_text}"
    text = normalize_text(text)

    for blocked in BLOCKED_TOPICS:
        blocked_clean = normalize_text(blocked)
        if blocked_clean in text:
            return True

    return False


def is_good_movie_candidate(candidate: dict) -> bool:
    text = normalize_text(f"{candidate.get('title', '')} {candidate.get('summary', '')}")

    has_movie_keyword = any(normalize_text(keyword) in text for keyword in MOVIE_ALLOWED_KEYWORDS)
    has_blocked_keyword = any(normalize_text(keyword) in text for keyword in MOVIE_BLOCKED_KEYWORDS)

    if has_blocked_keyword and not has_movie_keyword:
        return False

    return has_movie_keyword


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

    image = soup.select_one("article img, main img")
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

        if len(paragraph) < 60:
            continue

        if should_skip_paragraph(paragraph):
            continue

        cleaned.append(paragraph)

    text = "\n\n".join(cleaned)

    return {
        "text": text[:4500],
        "image": image,
        "imageAlt": image_alt,
    }


def extract_image_from_rss_entry(entry) -> tuple[str, str]:
    title = clean_text(getattr(entry, "title", ""))

    media_content = getattr(entry, "media_content", None)
    if media_content and isinstance(media_content, list):
        for media in media_content:
            if isinstance(media, dict) and media.get("url"):
                return clean_text(media.get("url")), title

    media_thumbnail = getattr(entry, "media_thumbnail", None)
    if media_thumbnail and isinstance(media_thumbnail, list):
        for media in media_thumbnail:
            if isinstance(media, dict) and media.get("url"):
                return clean_text(media.get("url")), title

    links = getattr(entry, "links", [])
    for link in links:
        if isinstance(link, dict):
            href = clean_text(link.get("href", ""))
            link_type = clean_text(link.get("type", ""))
            if href and link_type.startswith("image/"):
                return href, title

    return "", ""


def get_listing_candidates(url: str, source_name: str, category: str) -> list[dict]:
    try:
        html = request_text(url)
    except Exception as error:
        write_report(f"[ERROR] No se pudo leer listado: {url} | {error}")
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

        if "/futbol" not in parsed.path:
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
            write_report(f"[SKIP] Candidato bloqueado desde listado: {title}")
            continue

        candidates.append(candidate)

    write_report(f"[INFO] Candidatos encontrados en listado {source_name}: {len(candidates)}")

    return candidates


def get_rss_candidates(url: str, source_name: str, category: str) -> list[dict]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as error:
        write_report(f"[ERROR] No se pudo leer RSS: {url} | {error}")
        return []

    candidates = []
    seen = set()

    for entry in feed.entries:
        title = clean_text(getattr(entry, "title", ""))
        link = clean_text(getattr(entry, "link", ""))
        summary = clean_text(getattr(entry, "summary", ""))

        if not title or not link:
            continue

        if link in seen:
            continue

        seen.add(link)

        image, image_alt = extract_image_from_rss_entry(entry)

        candidate = {
            "title": title,
            "url": link,
            "summary": summary,
            "sourceName": source_name,
            "category": category,
            "image": image,
            "imageAlt": image_alt or title,
        }

        if is_blocked_topic(candidate):
            write_report(f"[SKIP] Candidato bloqueado desde RSS: {title}")
            continue

        candidates.append(candidate)

    write_report(f"[INFO] Candidatos encontrados en RSS {source_name}: {len(candidates)}")

    return candidates


def build_prompt(candidate: dict, source_text: str, content_type: str) -> str:
    app_context = """
TELELATINO es una app de entretenimiento para Android con canales en vivo,
eventos deportivos, películas y estrenos. Tiene 7 días de prueba gratis al
registrarse y plan VIP de 6 meses por 6 USD. La web usa artículos informativos
para atraer usuarios y al final de cada artículo ya existe un CTA automático
para descargar la app.
"""

    base_rules = """
Reglas importantes:
- No copies frases literales de la fuente.
- No publiques el artículo como exclusiva propia.
- Redacta con estructura nueva, valor añadido y tono natural.
- No agregues el CTA de descarga, porque la web ya lo inserta automáticamente.
- No uses markdown H1.
- Usa subtítulos H2.
- Escribe entre 450 y 750 palabras.
- No inventes datos concretos, resultados, fechas o declaraciones si no aparecen en la fuente.
- Mantén un estilo informativo, claro y útil.
- Responde SOLO JSON válido, sin markdown externo.
"""

    if content_type == "movies":
        type_instructions = """
Tipo de artículo: cine, películas o estrenos.

Objetivo:
Crear un artículo útil para usuarios interesados en películas, estrenos,
tráilers, cartelera y sinopsis.

Estructura recomendada:
- Introducción breve.
- Sinopsis o explicación de la película si hay una película concreta.
- Por qué puede llamar la atención.
- Qué tipo de público puede disfrutarla.
- Cierre informativo.

Importante:
Si la fuente habla de una película concreta, marca is_specific_movie como true,
coloca el nombre de esa película en main_movie_title y genera una búsqueda exacta
para YouTube.

Si la fuente habla de muchas películas, plataforma, industria, series o proyectos
generales, marca is_specific_movie como false y deja youtube_search_query vacío.
"""
    else:
        type_instructions = """
Tipo de artículo: noticia deportiva de fútbol.

Objetivo:
Crear una noticia deportiva clara y útil. Explica el contexto, el punto principal
y por qué puede ser relevante para usuarios que siguen fútbol, jugadores,
clubes, selecciones o torneos.
"""

    return f"""
Eres redactor SEO para la web TELELATINO.

Contexto de TELELATINO:
{app_context}

Fuente consultada:
Nombre: {candidate["sourceName"]}
URL: {candidate["url"]}
Título original: {candidate["title"]}
Resumen de la fuente: {candidate.get("summary", "")}

Texto de apoyo de la fuente, solo para entender contexto:
{source_text[:3000]}

{type_instructions}

{base_rules}

Formato JSON exacto:
{{
  "title": "Título SEO propio",
  "description": "Meta descripción de máximo 155 caracteres",
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


def generate_with_gemini(candidate: dict, source_text: str, content_type: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en variables de entorno o GitHub Secrets.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = build_prompt(candidate, source_text, content_type)

    last_error = None

    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )

            data = parse_json_response(response.text or "")

            required = ["title", "description", "body"]

            for key in required:
                if key not in data or not clean_text(str(data.get(key, ""))):
                    raise ValueError(f"Respuesta de Gemini incompleta. Falta: {key}")

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
                    data["tags"] = ["películas", "estrenos", "entretenimiento"]
                else:
                    data["tags"] = ["deportes", "fútbol", "noticias"]

            data["is_specific_movie"] = bool(data.get("is_specific_movie", False))
            data["main_movie_title"] = clean_text(data.get("main_movie_title", ""))
            data["youtube_search_query"] = clean_text(data.get("youtube_search_query", ""))

            return data

        except Exception as error:
            last_error = error
            write_report(f"[WARN] Gemini intento {attempt}/3 falló: {error}")

            if attempt < 3:
                time.sleep(8 * attempt)

    raise RuntimeError(f"Gemini falló después de 3 intentos: {last_error}")


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
        "maxResults": 1,
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

    item = items[0]
    video_id = item.get("id", {}).get("videoId")
    title = item.get("snippet", {}).get("title", "")

    if not video_id:
        return None

    title_clean = clean_text(title)

    write_report(f"[OK] Tráiler encontrado: {title_clean}")

    return {
        "youtubeVideoId": video_id,
        "youtubeVideoTitle": title_clean or "Tráiler oficial",
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
    today = datetime.now(timezone.utc).date().isoformat()

    base_slug = slugify(article["title"])
    short_hash = url_hash(candidate["url"])[:6]

    filename = f"{base_slug}-{today}-{short_hash}.md"

    target_dir = NEWS_DIR if collection == "noticias" else BLOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename

    tags = article.get("tags") or []
    if not tags:
        tags = ["telelatino"]

    image = article_data.get("image") or candidate.get("image") or DEFAULT_IMAGE
    image_alt = article_data.get("imageAlt") or candidate.get("imageAlt") or article["title"]

    frontmatter = [
        "---",
        f"title: {yaml_string(article['title'])}",
        f"description: {yaml_string(article['description'])}",
        f"pubDate: {today}",
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
        if source_type == "rss":
            all_candidates.extend(get_rss_candidates(url, source_name, category))
        elif source_type == "listing":
            all_candidates.extend(get_listing_candidates(url, source_name, category))
        else:
            write_report(f"[WARN] Tipo de fuente desconocido: {source_type}")

    return all_candidates


def run_group(name: str, config: dict, processed: dict) -> int:
    if not config.get("enabled", True):
        write_report(f"[INFO] Grupo desactivado: {name}")
        return 0

    collection = config.get("targetCollection", "blog")
    daily_limit = int(config.get("dailyLimit", 1))

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

        if content_type == "movies" and not is_good_movie_candidate(candidate):
            write_report(f"[SKIP] No parece artículo de película concreta/cine: {candidate['title']}")
            processed.setdefault("processed", {})[article_key] = {
                "url": candidate["url"],
                "status": "skipped_not_movie",
                "date": datetime.now(timezone.utc).isoformat(),
            }
            continue

        write_report(f"[INFO] Procesando: {candidate['title']}")
        write_report(f"[INFO] URL: {candidate['url']}")

        article_data = extract_article_data(candidate["url"])
        source_text = article_data.get("text", "")

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
            processed.setdefault("processed", {})[article_key] = {
                "url": candidate["url"],
                "status": "skipped_no_text",
                "date": datetime.now(timezone.utc).isoformat(),
            }
            continue

        try:
            article = generate_with_gemini(candidate, source_text, content_type)
        except Exception as error:
            write_report(f"[ERROR] Gemini falló: {error}")
            continue

        youtube_data = None

        if content_type == "movies":
            if article.get("is_specific_movie") and article.get("youtube_search_query"):
                youtube_data = search_youtube_trailer(article["youtube_search_query"])
            else:
                write_report("[INFO] Sin tráiler: el artículo no trata una película concreta.")

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
            "image": article_data.get("image") or candidate.get("image") or DEFAULT_IMAGE,
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