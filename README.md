# AJPLAY SERIES 24/7

Repositorio independiente para el catálogo de series/canales 24/7 de AJPLAY.

Cada registro representa una serie/canal y un único stream continuo. No se manejan temporadas ni episodios individuales.

## Estructura

```text
.
├── urls.txt
├── extractor.py
├── requirements.txt
├── base/.gitkeep
├── series/.gitkeep
├── category_list.json
└── .github/workflows/extractor.yml
```

## Formato
`urls.txt` contiene un array JSON, con un objeto por serie/canal. Cada entrada mantiene un único `URL_DIRECTA`. Las URLs firmadas no deben reconstruirse ni modificarse.

Campos compatibles: `CATEGORIA`, `TITULO`, `FECHA`, `PORTADA`, `BACKDROP`, `GENERO`, `RATING`, `FRASE_PROMOCIONAL`, `SINOPSIS`, `PLATAFORMA`, `URLS`, `URLS_DIRECTAS`, `URL_DIRECTA`, `METODO`.

El workflow actualiza solamente `base/`, `series/` y `category_list.json`. No toca COLECCION-2.0 ni la tabla `peliculas`. Nunca elimina `urls.txt`. Se ejecuta al cambiar el código o `urls.txt`, cada 2 horas (UTC), y manualmente.
