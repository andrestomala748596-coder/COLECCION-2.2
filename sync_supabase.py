"""Publica series en Supabase usando el mismo flujo versionado por lotes de COLECCION-2.1."""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://nyjgdfqxodcmcsdaprzi.supabase.co").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
COMMIT_SHA = os.environ.get("GITHUB_SHA", "").strip()
BATCH_SIZE = 50


def text_value(value):
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def number_value(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def integer_value(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else None
    except (ValueError, TypeError):
        return None


def date_value(value):
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def load_catalog():
    folder = ROOT / "series"
    files = sorted(folder.glob("*.json"))
    if not files:
        raise RuntimeError("ERROR: no hay JSON en series/")
    rows = {}
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else None
        if items is None:
            raise RuntimeError(f"Formato JSON inesperado en {path}")
        for item in items:
            if not isinstance(item, dict):
                continue
            category = str(item.get("CATEGORIA") or item.get("categoria") or path.stem).strip() or path.stem
            video_id = text_value(item.get("ID_VIDEO") or item.get("ID_OKRU"))
            title = text_value(item.get("TITULO")) or "Sin título"
            key = str(video_id or f"{category}:{title}")
            rows[(key, category)] = {
                "id_video": video_id,
                "plataforma": text_value(item.get("PLATAFORMA")),
                "titulo": title,
                "fecha": date_value(item.get("FECHA")),
                "portada": text_value(item.get("PORTADA")),
                "backdrop": text_value(item.get("BACKDROP")),
                "genero": text_value(item.get("GENERO")),
                "rating": number_value(item.get("RATING")),
                "duracion": integer_value(item.get("DURACION")),
                "frase_promocional": text_value(item.get("FRASE_PROMOCIONAL")),
                "sinopsis": text_value(item.get("SINOPSIS")),
                "actores": text_value(item.get("ACTORES")),
                "director": text_value(item.get("DIRECTOR")),
                "trailer": text_value(item.get("TRAILER")),
                "urls": [str(x) for x in (item.get("URLS") if isinstance(item.get("URLS"), list) else item.get("URLS_OKRU", [])) if isinstance(x, str)],
                "metodo": text_value(item.get("METODO")),
                "urls_directas": [str(x) for x in item.get("URLS_DIRECTAS", []) if isinstance(x, str)] if isinstance(item.get("URLS_DIRECTAS"), list) else [],
                "url_directa": text_value(item.get("URL_DIRECTA")),
                "extracted_by_url": item.get("_EXTRACTED_BY_URL") if isinstance(item.get("_EXTRACTED_BY_URL"), dict) else item.get("EXTRACTED_BY_URL") if isinstance(item.get("EXTRACTED_BY_URL"), dict) else {},
                "categoria": category,
            }
    records = list(rows.values())
    if not records:
        raise RuntimeError("ERROR: catálogo de series vacío; no se publicará")
    return records, len(files)


def main():
    if not SERVICE_KEY:
        raise RuntimeError("Falta el secreto SUPABASE_SERVICE_ROLE_KEY")
    records, file_count = load_catalog()
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    session = requests.Session()

    def api(method, path, **kwargs):
        response = session.request(method, f"{SUPABASE_URL}/rest/v1/{path}", headers=headers, timeout=180, **kwargs)
        if not response.ok:
            raise RuntimeError(f"Supabase HTTP {response.status_code}: {response.text[:3000]}")
        return response

    # Igual que COLECCION-2.1: crear versión primero, cargar lotes y activarla al final.
    start = api(
        "POST",
        "series_catalogo_versiones?select=id",
        headers={**headers, "Prefer": "return=representation"},
        json={"estado": "preparando", "commit_sha": COMMIT_SHA or None, "total_series": len(records)},
    ).json()
    if not isinstance(start, list) or not start or not start[0].get("id"):
        raise RuntimeError(f"Supabase no devolvió el ID de versión: {start}")
    version_id = start[0]["id"]
    print(f"Versión de series creada: {version_id}")

    for offset in range(0, len(records), BATCH_SIZE):
        batch = records[offset:offset + BATCH_SIZE]
        for row in batch:
            row["version_id"] = version_id
        api("POST", "series", headers={**headers, "Prefer": "return=minimal"}, json=batch)
        print(f"Lote {offset // BATCH_SIZE + 1}: {len(batch)} series insertadas")

    result = api(
        "POST",
        "rpc/ajplay_publish_series_catalog_version",
        json={"p_version_id": version_id},
    ).json()
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(f"Respuesta inesperada al activar versión: {result}")
    print(f"SUPABASE_SYNC_OK archivos={file_count} series={result.get('total_series')} version={version_id} commit={COMMIT_SHA}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
