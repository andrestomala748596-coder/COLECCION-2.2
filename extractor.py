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

def extract(url: str, platform: str) -> str | None:
    headers = {"User-Agent": UA, "Referer": url}
    if platform == "ok_ru":
        try:
            response = requests.get(url, headers=headers, timeout=30); response.raise_for_status()
            page = html.unescape(response.text).replace(r"\/", "/")
            match = re.search(r'"metadata"\s*:\s*(\{.*?\})\s*,\s*"[^"]+"', page, re.S)
            if match:
                data = json.loads(match.group(1))
                candidates = [v.get("url") for v in data.get("videos", []) if isinstance(v, dict) and v.get("url")]
                if candidates: return candidates[-1]
        except (requests.RequestException, ValueError, TypeError): pass
    try:
        result = subprocess.run(["yt-dlp", "--no-warnings", "--no-playlist", "--skip-download", "-g", url],
                                capture_output=True, text=True, timeout=75, check=False)
    except (OSError, subprocess.TimeoutExpired): return None
    if result.returncode == 0:
        return next((line.strip() for line in result.stdout.splitlines()
                     if line.strip().startswith(("http://", "https://"))), None)
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
