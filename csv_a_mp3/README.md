# CSV a MP3

Lee un CSV, busca cada fila en YouTube y descarga el primer resultado como `.mp3`, sin hacer preguntas.

## Instalación

1. Python 3.9+
2. `pip install -r requirements.txt`
3. Instalar **ffmpeg** (Windows: `winget install ffmpeg`, macOS: `brew install ffmpeg`, Linux: `sudo apt install ffmpeg`)

## Uso

```bash
python descargar.py ejemplo.csv
python descargar.py lista.csv -o carpeta_salida -c titulo -q 320
```

## Formato del CSV

- Con cabecera: usa las columnas `titulo`/`busqueda`/`cancion` y, si existe, `artista` (se combinan como `artista - titulo`).
- Sin cabecera: usa la primera columna de cada fila.
- Acepta separadores `,` `;` o tabulador.

Si una búsqueda falla, la salta y la muestra al final en el resumen.

> Úsalo solo con contenido que tengas derecho a descargar (licencias libres, Creative Commons, contenido propio). Descargar música con copyright puede infringir las condiciones de YouTube.
