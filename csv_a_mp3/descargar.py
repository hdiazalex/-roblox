#!/usr/bin/env python3
"""
Lee un CSV, busca cada entrada en YouTube y descarga el audio en .mp3.

Uso:
    python descargar.py canciones.csv
    python descargar.py canciones.csv -o mi_carpeta -c titulo

El CSV puede tener cabecera (se usa la columna indicada con -c, o
"busqueda"/"titulo"/"cancion" si existen) o no tenerla (se usa la
primera columna). Si una columna "artista" existe, se añade a la búsqueda.

Requisitos: pip install yt-dlp  +  ffmpeg instalado en el sistema.
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

try:
    from yt_dlp import YoutubeDL
except ImportError:
    sys.exit("Falta yt-dlp. Instálalo con: pip install yt-dlp")

COLUMNAS_BUSQUEDA = ("busqueda", "titulo", "cancion", "query", "title", "song")
COLUMNAS_ARTISTA = ("artista", "artist", "autor")


def leer_busquedas(ruta_csv, columna=None):
    """Devuelve la lista de textos a buscar a partir del CSV."""
    with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
        muestra = f.read(4096)
        f.seek(0)
        try:
            dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
        except csv.Error:
            dialecto = csv.excel
        filas = [fila for fila in csv.reader(f, dialecto) if any(c.strip() for c in fila)]

    if not filas:
        return []

    cabecera = [c.strip().lower() for c in filas[0]]
    col_busqueda = None
    col_artista = None

    if columna:
        if columna.lower() not in cabecera:
            sys.exit(f"La columna '{columna}' no existe. Columnas: {filas[0]}")
        col_busqueda = cabecera.index(columna.lower())
    else:
        col_busqueda = next((cabecera.index(c) for c in COLUMNAS_BUSQUEDA if c in cabecera), None)
    col_artista = next((cabecera.index(c) for c in COLUMNAS_ARTISTA if c in cabecera), None)

    if col_busqueda is None and col_artista is None:
        # Sin cabecera reconocible: todas las filas son datos, primera columna
        return [fila[0].strip() for fila in filas if fila[0].strip()]

    busquedas = []
    for fila in filas[1:]:
        partes = []
        if col_artista is not None and col_artista < len(fila):
            partes.append(fila[col_artista].strip())
        if col_busqueda is not None and col_busqueda < len(fila):
            partes.append(fila[col_busqueda].strip())
        texto = " - ".join(p for p in partes if p)
        if texto:
            busquedas.append(texto)
    return busquedas


def descargar(busquedas, carpeta, calidad):
    carpeta.mkdir(parents=True, exist_ok=True)
    opciones = {
        "format": "bestaudio/best",
        "outtmpl": str(carpeta / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(calidad),
        }],
    }

    ok, fallos = 0, []
    with YoutubeDL(opciones) as ydl:
        for i, texto in enumerate(busquedas, 1):
            print(f"[{i}/{len(busquedas)}] Buscando: {texto}")
            try:
                info = ydl.extract_info(f"ytsearch1:{texto}", download=True)
                entradas = info.get("entries") or []
                if not entradas:
                    raise RuntimeError("sin resultados")
                print(f"    -> Descargado: {entradas[0].get('title')}.mp3")
                ok += 1
            except Exception as e:  # seguir con la siguiente sin preguntar
                print(f"    !! Error: {e}")
                fallos.append(texto)

    print(f"\nTerminado: {ok} descargadas, {len(fallos)} fallidas. Carpeta: {carpeta.resolve()}")
    if fallos:
        print("Fallidas:")
        for t in fallos:
            print(f"  - {t}")
    return 0 if not fallos else 1


def main():
    p = argparse.ArgumentParser(description="Descarga en .mp3 las búsquedas de un CSV desde YouTube.")
    p.add_argument("csv", type=Path, help="Ruta al archivo CSV")
    p.add_argument("-o", "--salida", type=Path, default=Path("descargas"), help="Carpeta de salida (por defecto: descargas)")
    p.add_argument("-c", "--columna", help="Nombre de la columna con el texto a buscar")
    p.add_argument("-q", "--calidad", type=int, default=192, help="Kbps del mp3 (por defecto: 192)")
    args = p.parse_args()

    if not args.csv.is_file():
        sys.exit(f"No encuentro el archivo: {args.csv}")
    if shutil.which("ffmpeg") is None:
        sys.exit("Falta ffmpeg. Instálalo (https://ffmpeg.org) y asegúrate de que está en el PATH.")

    busquedas = leer_busquedas(args.csv, args.columna)
    if not busquedas:
        sys.exit("El CSV no contiene ninguna búsqueda.")
    sys.exit(descargar(busquedas, args.salida, args.calidad))


if __name__ == "__main__":
    main()
