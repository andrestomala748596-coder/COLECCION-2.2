"""Extractor de URL para AJPLAY SERIES 24/7.
Un registro es un canal/serie y conserva una sola URL de emisión continua.
"""
from __future__ import annotations
import html, json, re, subprocess
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"

def normalize(url: str) -> str:
    url = html.unescape(url).strip().replace(r"\/", "/")
    url = url.replace(r"\u0026", "&").replace(r"\u003D", "=")
    return "https:" + url if url.startswith("//") else url

def is_direct(url: str, item: dict) -> bool:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")): return False
    platform = str(item.get("PLATAFORMA", "")).lower()
    if "budtv direct" in platform or "directo" in platform: return True
    return bool(re.search(r"\.(?:mp4|m3u8|mkv|mpd|ts)(?:$|/)", urlparse(url).path, re.I))

def classify(url: str, item: dict) -> str:
    if is_direct(url, item): return "directo"
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("ok.ru"): return "ok_ru"
    if host.endswith("vimeos.net"): return "vimeos"
    if host.endswith(("tokyvideo.com", "vk.com", "vkvideo.ru")): return "tokyvideo"
    if host.endswith("videa.hu"): return "videa_hu"
    return "directo"

def _metadata_object(page: str) -> dict | None:
    """Extrae metadata como JSON balanceado, respetando strings y escapes."""
    match = re.search(r'"metadata"\s*:\s*\{', page, re.I)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    in_string = False
    escape = False
    end = -1
    for index in range(start, len(page)):
        char = page[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        return None
    raw = page[start:end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _okru_quality(video: dict) -> float:
    """Puntúa resolución, tipo/calidad declarada y bitrate."""
    def number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    width = number(video.get("width"))
    height = number(video.get("height"))
    bitrate = number(video.get("bitrate"))
    score = width * height * 1000.0
    try:
        score += int(video.get("type")) * 1_000_000.0
    except (TypeError, ValueError):
        levels = {
            "ultra": 7, "2160": 7, "4k": 7,
            "quadhd": 6, "1440": 6,
            "full_hd": 5, "fullhd": 5, "1080": 5,
            "hd": 4, "720": 4,
            "sd": 3, "480": 3,
            "low": 2, "360": 2,
            "lowest": 1, "240": 1,
            "mobile": 0, "144": 0,
        }
        name = str(video.get("name", "")).lower()
        for token, level in levels.items():
            if token in name:
                score += level * 1_000_000.0
                break
    return score + bitrate


def _extract_okru(url: str) -> str | None:
    """Obtiene la variante reproducible de mayor calidad publicada por OK.ru."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not (host == "ok.ru" or host.endswith(".ok.ru")):
        return None

    headers = {
        "User-Agent": UA,
        "Referer": "https://ok.ru/",
        "Accept-Language": "es,en;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    page = html.unescape(response.text)
    page = page.replace(r"\/", "/").replace(r"\u0026", "&").replace(r"\u003D", "=")
    metadata = _metadata_object(page)
    if not metadata:
        return None

    videos = metadata.get("videos", [])
    candidates = []
    if isinstance(videos, list):
        for video in videos:
            if not isinstance(video, dict):
                continue
            direct = video.get("url")
            if not isinstance(direct, str):
                continue
            direct = normalize(direct.strip())
            if direct.startswith(("http://", "https://")):
                candidates.append((_okru_quality(video), direct))

    if candidates:
        return max(candidates, key=lambda candidate: candidate[0])[1]

    # Algunos formatos de página publican HLS/DASH fuera de la lista videos.
    for key in ("ondemandHls", "ondemandDash"):
        direct = metadata.get(key)
        if isinstance(direct, str):
            direct = normalize(direct.strip())
            if direct.startswith(("http://", "https://")):
                return direct
    return None


def extract(url: str, platform: str) -> str | None:
    if platform == "ok_ru":
        try:
            return _extract_okru(url)
        except (requests.RequestException, ValueError, TypeError):
            return None

    try:
        result = subprocess.run(
            ["yt-dlp", "--no-warnings", "--no-playlist", "--skip-download", "-g", url],
            capture_output=True, text=True, timeout=75, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return next(
            (line.strip() for line in result.stdout.splitlines()
             if line.strip().startswith(("http://", "https://"))),
            None
        )
    return None

def source_urls(item: dict) -> list[str]:
    value = item.get("URLS", item.get("URL", item.get("url", [])))
    if isinstance(value, str): value = [value]
    return [normalize(v) for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []

def process(item: dict, cache: dict) -> dict:
    result = dict(item)
    # Single 24/7 stream: explicit URL_DIRECTA takes precedence and is never mutated.
    current = result.get("URL_DIRECTA")
    if isinstance(current, str) and current.startswith(("http://", "https://")):
        result["URLS_DIRECTAS"] = [current]
        return result
    previous = result.get("URLS_DIRECTAS", [])
    if isinstance(previous, str): previous = [previous]
    previous = [u for u in previous if isinstance(u, str) and u.startswith(("http://", "https://"))]
    for original in source_urls(result):
        platform = classify(original, result)
        direct = original if platform == "directo" else cache.get(original)
        if not direct and platform != "directo":
            direct = extract(original, platform)
            if direct: cache[original] = direct
        if direct and direct not in previous: previous.append(direct)
    chosen = previous[0] if previous else ""
    result["URL_DIRECTA"] = chosen
    result["URLS_DIRECTAS"] = [chosen] if chosen else []
    return result

def main() -> None:
    source = ROOT / "urls.txt"
    if not source.exists() or not source.read_text(encoding="utf-8").strip():
        raise SystemExit("ERROR: urls.txt no existe o está vacío.")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list): raise SystemExit("ERROR: urls.txt debe contener una lista JSON.")
    base = ROOT / "base"; base.mkdir(exist_ok=True)
    cache_file = base / "extracted_by_url.json"
    try: cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    except (OSError, ValueError): cache = {}
    if not isinstance(cache, dict): cache = {}
    grouped = {}
    for raw in data:
        if not isinstance(raw, dict): continue
        item = process(raw, cache)
        category = re.sub(r"[^A-Z0-9_-]+", "_", str(item.get("CATEGORIA", "GENERAL")).upper()).strip("_") or "GENERAL"
        grouped.setdefault(category, []).append(item)
    output = ROOT / "series"; output.mkdir(exist_ok=True)
    for category, entries in grouped.items():
        target = output / f"{category}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "category_list.json").write_text(json.dumps(sorted(grouped), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Series/canales procesados: {sum(len(v) for v in grouped.values())}")

if __name__ == "__main__": main()
