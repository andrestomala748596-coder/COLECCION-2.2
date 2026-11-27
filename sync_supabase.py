"""Publica el snapshot de series de COLECCION-2.2 en Supabase AJPLAY."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://nyjgdfqxodcmcsdaprzi.supabase.co").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
COMMIT_SHA = os.environ.get("GITHUB_SHA", "").strip()


def as_list(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def map_record(item: dict, source: Path) -> dict:
    direct = str(item.get("URL_DIRECTA") or "").strip()
    direct_urls = as_list(item.get("URLS_DIRECTAS"))
    if not direct and direct_urls:
        direct = direct_urls[0]
    if not direct.startswith(("http://", "https://")):
        raise ValueError(
            f"{source.name}: '{item.get('TITULO', 'Sin título')}' no tiene URL_DIRECTA válida"
        )

    source_urls = as_list(item.get("URLS"))
    if not source_urls:
        source_urls = as_list(item.get("URL"))
    if direct not in direct_urls:
        direct_urls.insert(0, direct)

    return {
        "id_video": item.get("ID_VIDEO"),
        "plataforma": item.get("PLATAFORMA"),
        "titulo": str(item.get("TITULO") or "").strip(),
        "fecha": item.get("FECHA") or None,
        "portada": item.get("PORTADA") or None,
        "backdrop": item.get("BACKDROP") or None,
        "genero": item.get("GENERO") or None,
        "rating": item.get("RATING"),
        "duracion": item.get("DURACION"),
        "frase_promocional": item.get("FRASE_PROMOCIONAL") or None,
        "sinopsis": item.get("SINOPSIS") or None,
        "actores": item.get("ACTORES") or None,
        "director": item.get("DIRECTOR") or None,
        "trailer": item.get("TRAILER") or None,
        "urls": source_urls,
        "metodo": item.get("METODO") or None,
        "urls_directas": direct_urls,
        "url_directa": direct,
        "extracted_by_url": item.get("EXTRACTED_BY_URL") or {},
        "categoria": item.get("CATEGORIA") or source.stem,
    }


def load_catalog() -> list[dict]:
    folder = ROOT / "series"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    if not files:
        raise RuntimeError("No hay JSON de catálogo dentro de series/")
    records = []
    errors = []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                raise ValueError("el JSON no contiene una lista")
            for item in data:
                if not isinstance(item, dict):
                    raise ValueError("hay un registro que no es un objeto JSON")
                records.append(map_record(item, file))
        except Exception as exc:
            errors.append(f"{file.name}: {exc}")
    if errors:
        raise RuntimeError("No se publicó el catálogo porque hay registros inválidos:\n- " + "\n- ".join(errors))
    if not records:
        raise RuntimeError("El catálogo de series está vacío; se canceló la publicación.")
    return records


def main() -> int:
    if not SERVICE_KEY:
        print(
            "ERROR: falta el secreto SUPABASE_SERVICE_ROLE_KEY en "
            "GitHub > Settings > Secrets and variables > Actions.",
            file=sys.stderr,
        )
        return 2

    records = load_catalog()
    endpoint = f"{SUPABASE_URL}/rest/v1/rpc/publicar_catalogo_series"
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"p_series": records, "p_commit_sha": COMMIT_SHA or None}
    response = requests.post(endpoint, headers=headers, json=payload, timeout=180)
    if not response.ok:
        print(f"ERROR Supabase HTTP {response.status_code}: {response.text[:3000]}", file=sys.stderr)
        return 1

    try:
        result = response.json()
    except ValueError:
        print(f"ERROR: Supabase devolvió una respuesta no JSON: {response.text[:1000]}", file=sys.stderr)
        return 1

    if not isinstance(result, dict) or result.get("ok") is not True:
        print(f"ERROR: respuesta inesperada de Supabase: {result}", file=sys.stderr)
        return 1

    print(
        "SUPABASE_SYNC_OK "
        f"series={result.get('total_series')} "
        f"version={result.get('version_id')} "
        f"commit={result.get('commit_sha')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
