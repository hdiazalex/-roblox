#!/usr/bin/env python3
"""Descarga el audio de vídeos de YouTube en MP3 para construir un dataset.

Además del MP3 guarda un CSV con los metadatos de cada pista (título, autor,
licencia, duración, URL) para poder documentar el origen de los datos.

Uso:
    python descargar_audio.py URL [URL ...]
    python descargar_audio.py --lista urls.txt --solo-cc
"""
import argparse
import csv
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    sys.exit("Falta yt-dlp. Instálalo con: pip install -r requirements.txt")

CAMPOS_CSV = ["id", "titulo", "autor", "licencia", "duracion_s", "url", "archivo"]


def leer_urls(args):
    urls = list(args.urls)
    if args.lista:
        for linea in Path(args.lista).read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                urls.append(linea)
    return urls


def filtro_licencia(solo_cc):
    """Devuelve un match_filter de yt-dlp que descarta vídeos sin licencia CC."""
    def filtro(info, *, incomplete):
        if not solo_cc or incomplete:
            return None
        licencia = (info.get("license") or "").lower()
        if "creative commons" not in licencia:
            return f"Omitido (licencia: {info.get('license') or 'estándar de YouTube'})"
        return None
    return filtro


def main():
    parser = argparse.ArgumentParser(description="Descarga audio de YouTube en MP3.")
    parser.add_argument("urls", nargs="*", help="URLs de vídeos o listas de reproducción")
    parser.add_argument("-l", "--lista", help="Archivo de texto con una URL por línea")
    parser.add_argument("-o", "--salida", default="dataset", help="Carpeta de destino (por defecto: dataset)")
    parser.add_argument("-c", "--calidad", default="192", help="Bitrate MP3 en kbps (por defecto: 192)")
    parser.add_argument("--mono-16k", action="store_true",
                        help="Convierte a mono 16 kHz (formato habitual para modelos de voz)")
    parser.add_argument("--solo-cc", action="store_true",
                        help="Descarga solo vídeos con licencia Creative Commons")
    args = parser.parse_args()

    urls = leer_urls(args)
    if not urls:
        parser.error("indica al menos una URL o un archivo con --lista")

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    ruta_csv = salida / "metadatos.csv"
    nuevo_csv = not ruta_csv.exists()

    opciones = {
        "format": "bestaudio/best",
        "outtmpl": str(salida / "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": args.calidad,
        }],
        "match_filter": filtro_licencia(args.solo_cc),
        "download_archive": str(salida / ".descargados.txt"),  # evita repetir descargas
        "ignoreerrors": True,
        "quiet": False,
    }
    if args.mono_16k:
        opciones["postprocessor_args"] = {"extractaudio": ["-ac", "1", "-ar", "16000"]}

    with open(ruta_csv, "a", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
        if nuevo_csv:
            escritor.writeheader()

        def registrar(info):
            escritor.writerow({
                "id": info.get("id"),
                "titulo": info.get("title"),
                "autor": info.get("uploader"),
                "licencia": info.get("license") or "estándar de YouTube",
                "duracion_s": info.get("duration"),
                "url": info.get("webpage_url"),
                "archivo": f"{info.get('id')}.mp3",
            })
            f.flush()

        with yt_dlp.YoutubeDL(opciones) as ydl:
            for url in urls:
                info = ydl.extract_info(url, download=True)
                if not info:
                    continue
                for entrada in info.get("entries") or [info]:
                    if entrada and entrada.get("requested_downloads"):
                        registrar(entrada)

    print(f"\nListo. Audios y metadatos en: {salida.resolve()}")


if __name__ == "__main__":
    main()
