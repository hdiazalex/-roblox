#!/usr/bin/env python3
"""Biblioteca a MP3.

Convierte a MP3 las canciones de tu biblioteca de la app Música (Apple Music)
o de iTunes que estén guardadas en tu equipo y no tengan DRM: compras de la
iTunes Store, CDs importados y archivos que hayas añadido tú.

Las canciones de la suscripción de Apple Music vienen cifradas con FairPlay
(archivos .m4p). Este programa las detecta, no las toca y las apunta en el
informe para que sepas cuáles son.

Uso:
    python3 biblioteca_a_mp3.py                          # modo guiado
    python3 biblioteca_a_mp3.py Biblioteca.xml -o ~/MP3
    python3 biblioteca_a_mp3.py ~/Music/Music/Media -o ~/MP3

Requiere Python 3.9+ y ffmpeg.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import os
import plistlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import unicodedata
import xml.parsers.expat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote, urlparse

__version__ = "1.0.0"

AUDIO_EXTENSIONS = {
    ".aac", ".aif", ".aifc", ".aiff", ".caf", ".flac", ".m4a", ".m4b",
    ".m4p", ".mp3", ".ogg", ".opus", ".wav",
}
MP4_EXTENSIONS = {".m4a", ".m4b", ".m4p", ".mp4"}
# Tipos de "sample entry" de MP4 que indican contenido cifrado (FairPlay, CENC).
PROTECTED_SAMPLE_ENTRIES = {b"drms", b"drmi", b"enca", b"encv", b"enct", b"encs"}
# Cajas que hay que recorrer dentro de "moov" para llegar a "stsd".
MP4_CONTAINER_BOXES = {b"trak", b"mdia", b"minf", b"stbl"}
MAX_MOOV_BYTES = 64 * 1024 * 1024

QUALITY_ARGS = {
    "320": ["-b:a", "320k"],
    "256": ["-b:a", "256k"],
    "192": ["-b:a", "192k"],
    "128": ["-b:a", "128k"],
    "v0": ["-q:a", "0"],
    "v2": ["-q:a", "2"],
}
DEFAULT_QUALITY = "320"
DEFAULT_OUTPUT = Path.home() / "Music" / "MP3"
REPORT_NAME = "informe-mp3.csv"

# Estados que se muestran en pantalla y en el informe.
CONVERTED = "convertida"
COPIED = "copiada (ya era MP3)"
SIMULATED = "se convertiría"
EXISTS = "ya existía"
PROTECTED = "protegida con DRM"
NOT_DOWNLOADED = "no descargada"
MISSING = "archivo no encontrado"
FAILED = "error"
STATUS_ORDER = [CONVERTED, COPIED, SIMULATED, EXISTS, PROTECTED, NOT_DOWNLOADED, MISSING, FAILED]

EXPORT_HELP = """\
Cómo exportar tu biblioteca:
  • Mac (app Música):     Archivo > Biblioteca > Exportar biblioteca…
  • Windows (iTunes):     Archivo > Biblioteca > Exportar biblioteca…
  Guarda el archivo .xml y arrástralo aquí.
  Si tu app no tiene esa opción, arrastra la carpeta donde están tus canciones
  (en Mac suele ser ~/Música/Music/Media)."""

FFMPEG_HELP = """\
No encuentro ffmpeg, que es lo que hace la conversión a MP3.
  • Mac:      brew install ffmpeg      (https://brew.sh)
  • Windows:  winget install ffmpeg    (o copia ffmpeg.exe junto a este programa)
  • Linux:    sudo apt install ffmpeg
También puedes indicar dónde está con --ffmpeg /ruta/a/ffmpeg"""


class UserError(Exception):
    """Error que se explica al usuario sin traza."""


@dataclass
class Track:
    source: Optional[Path]
    title: str = ""
    artist: str = ""
    album_artist: str = ""
    album: str = ""
    genre: str = ""
    composer: str = ""
    year: Optional[int] = None
    track_number: Optional[int] = None
    track_count: Optional[int] = None
    disc_number: Optional[int] = None
    disc_count: Optional[int] = None
    compilation: bool = False
    # Lo que dice el XML: protegida, de la suscripción de Apple Music, comprada.
    protected: bool = False
    apple_music: bool = False
    purchased: bool = False
    # Modo carpeta: ruta del archivo relativa a la carpeta de origen.
    relative_source: Optional[Path] = None

    @property
    def label(self) -> str:
        title = self.title or (self.source.stem if self.source else "")
        artist = self.artist or self.album_artist
        return f"{artist} - {title}" if artist else title


@dataclass
class Result:
    track: Track
    status: str
    dest: Optional[Path] = None
    detail: str = ""


Job = Tuple[Track, Path]


# --- Lectura de la biblioteca -------------------------------------------------

def load_library_xml(path: Path, playlists: Sequence[str] = ()) -> List[Track]:
    """Lee la biblioteca exportada desde la app Música o iTunes."""
    try:
        with open(path, "rb") as fh:
            library = plistlib.load(fh)
    except (OSError, ValueError, xml.parsers.expat.ExpatError) as exc:
        raise UserError(f"No puedo leer {path} como biblioteca exportada: {exc}") from exc

    raw_tracks = library.get("Tracks") if isinstance(library, dict) else None
    if not isinstance(raw_tracks, dict):
        raise UserError(f"{path} no parece una biblioteca exportada de Música/iTunes.")

    if playlists:
        entries = _playlist_entries(library, raw_tracks, playlists)
    else:
        entries = list(raw_tracks.values())
    return [_track_from_entry(entry) for entry in entries if _is_audio_entry(entry)]


def _playlist_entries(library: dict, raw_tracks: dict, names: Sequence[str]) -> List[dict]:
    wanted = {name.casefold(): name for name in names}
    found: Set[str] = set()
    seen: Set[object] = set()
    entries = []
    for playlist in library.get("Playlists", []):
        key = str(playlist.get("Name", "")).casefold()
        if key not in wanted:
            continue
        found.add(key)
        for item in playlist.get("Playlist Items", []):
            track_id = item.get("Track ID")
            if track_id in seen:
                continue
            seen.add(track_id)
            entry = raw_tracks.get(str(track_id))
            if entry:
                entries.append(entry)
    missing = [name for key, name in wanted.items() if key not in found]
    if missing:
        raise UserError("No encontré estas listas en la biblioteca: " + ", ".join(missing))
    return entries


def _is_audio_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("Track Type") == "URL":  # emisoras de radio por internet
        return False
    return not any(entry.get(key) for key in ("Has Video", "Movie", "TV Show", "Music Video"))


def _track_from_entry(entry: dict) -> Track:
    location = entry.get("Location")
    return Track(
        source=file_url_to_path(location) if location else None,
        title=_text(entry.get("Name")),
        artist=_text(entry.get("Artist")),
        album_artist=_text(entry.get("Album Artist")),
        album=_text(entry.get("Album")),
        genre=_text(entry.get("Genre")),
        composer=_text(entry.get("Composer")),
        year=_positive_int(entry.get("Year")),
        track_number=_positive_int(entry.get("Track Number")),
        track_count=_positive_int(entry.get("Track Count")),
        disc_number=_positive_int(entry.get("Disc Number")),
        disc_count=_positive_int(entry.get("Disc Count")),
        compilation=bool(entry.get("Compilation")),
        protected=bool(entry.get("Protected")),
        apple_music=bool(entry.get("Apple Music")),
        purchased=bool(entry.get("Purchased")),
    )


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _positive_int(value: object) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def file_url_to_path(url: str) -> Optional[Path]:
    """Convierte un 'Location' del XML (file://...) en una ruta del sistema."""
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:", path):  # file://localhost/C:/Users/...
        path = path[1:]
    elif parsed.netloc not in ("", "localhost"):  # ruta de red de Windows
        path = "//" + parsed.netloc + path
    return Path(path)


def scan_folder(root: Path, exclude: Optional[Path] = None) -> List[Track]:
    """Busca archivos de audio en una carpeta y sus subcarpetas."""
    excluded = exclude.resolve() if exclude else None
    tracks = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".") and (current / name).resolve() != excluded
        )
        for name in sorted(filenames):
            path = current / name
            if name.startswith(".") or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            tracks.append(Track(source=path, relative_source=path.relative_to(root)))
    return tracks


# --- Detección de DRM ---------------------------------------------------------

def is_drm_protected(path: Path) -> bool:
    """True si el archivo está cifrado (FairPlay de Apple Music u otro DRM)."""
    suffix = path.suffix.lower()
    if suffix == ".m4p":
        return True
    if suffix not in MP4_EXTENSIONS:
        return False
    try:
        with open(path, "rb") as fh:
            moov = _read_top_level_box(fh, b"moov")
    except OSError:
        return False
    return moov is not None and _has_protected_entry(moov)


def _read_top_level_box(fh: BinaryIO, wanted: bytes) -> Optional[bytes]:
    fh.seek(0, os.SEEK_END)
    file_size = fh.tell()
    offset = 0
    while offset + 8 <= file_size:
        fh.seek(offset)
        size, box_type = struct.unpack(">I4s", fh.read(8))
        header_len = 8
        if size == 1:
            extended = fh.read(8)
            if len(extended) < 8:
                return None
            size = struct.unpack(">Q", extended)[0]
            header_len = 16
        elif size == 0:
            size = file_size - offset
        if size < header_len:
            return None
        if box_type == wanted:
            body_len = size - header_len
            return fh.read(body_len) if body_len <= MAX_MOOV_BYTES else None
        offset += size
    return None


def _iter_boxes(data: bytes, start: int, end: int) -> Iterator[Tuple[bytes, int, int]]:
    pos = start
    while pos + 8 <= end:
        size, box_type = struct.unpack_from(">I4s", data, pos)
        header_len = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = struct.unpack_from(">Q", data, pos + 8)[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len or pos + size > end:
            return
        yield box_type, pos + header_len, pos + size
        pos += size


def _has_protected_entry(data: bytes, start: int = 0, end: Optional[int] = None) -> bool:
    end = len(data) if end is None else end
    for box_type, body_start, body_end in _iter_boxes(data, start, end):
        if box_type in MP4_CONTAINER_BOXES:
            if _has_protected_entry(data, body_start, body_end):
                return True
        elif box_type == b"stsd":
            # versión + flags (4 bytes) y número de entradas (4 bytes)
            for entry_type, _, _ in _iter_boxes(data, body_start + 8, body_end):
                if entry_type in PROTECTED_SAMPLE_ENTRIES:
                    return True
    return False


# --- Planificación ------------------------------------------------------------

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_name(text: str, max_len: int = 120) -> str:
    """Nombre de archivo o carpeta válido en Mac, Windows y Linux."""
    text = unicodedata.normalize("NFC", text)
    text = _INVALID_CHARS.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:max_len].rstrip(". ")
    if not text:
        return "_"
    if text.startswith(".") or text.split(".")[0].upper() in _RESERVED_NAMES:
        text = "_" + text
    return text


def destination_for(track: Track) -> Path:
    """Ruta del MP3 relativa a la carpeta de salida."""
    if track.relative_source is not None:
        folders = [safe_name(part) for part in track.relative_source.parent.parts]
        return Path(*folders, safe_name(track.relative_source.stem) + ".mp3")

    artist = track.album_artist or ("Varios artistas" if track.compilation else track.artist)
    album = track.album or "Álbum desconocido"
    title = track.title or (track.source.stem if track.source else "Sin título")
    prefix = ""
    if track.track_number:
        prefix = f"{track.track_number:02d} "
        if track.disc_number and (track.disc_count or 0) > 1:
            prefix = f"{track.disc_number}-{prefix}"
    return Path(safe_name(artist or "Artista desconocido"), safe_name(album), safe_name(prefix + title) + ".mp3")


def _claim_unique(dest: Path, used: Set[str]) -> Path:
    # Sin distinguir mayúsculas: los discos de Mac y Windows no lo hacen.
    candidate, n = dest, 2
    while candidate.as_posix().casefold() in used:
        candidate = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    used.add(candidate.as_posix().casefold())
    return candidate


def skip_reason(track: Track) -> Optional[Tuple[str, str]]:
    """Motivo por el que una canción no se puede convertir, o None."""
    if track.source is None:
        if track.apple_music and not track.purchased:
            return PROTECTED, "de la suscripción de Apple Music, sin archivo en tu equipo"
        return NOT_DOWNLOADED, "solo está en la nube: descárgala en la app Música y repite"
    if not track.source.is_file():
        return MISSING, str(track.source)
    if track.protected or is_drm_protected(track.source):
        return PROTECTED, "cifrada con FairPlay (Apple Music), no se puede convertir"
    return None


def plan(tracks: Sequence[Track], out_dir: Path, overwrite: bool) -> Tuple[List[Result], List[Job]]:
    """Separa las canciones en descartadas (con su motivo) y pendientes."""
    skipped: List[Result] = []
    pending: List[Job] = []
    used: Set[str] = set()
    for track in tracks:
        reason = skip_reason(track)
        if reason:
            skipped.append(Result(track, reason[0], detail=reason[1]))
            continue
        dest = out_dir / _claim_unique(destination_for(track), used)
        if dest.exists() and not overwrite:
            skipped.append(Result(track, EXISTS, dest))
        else:
            pending.append((track, dest))
    return skipped, pending


# --- Conversión ---------------------------------------------------------------

def metadata_tags(track: Track) -> List[Tuple[str, str]]:
    """Etiquetas del XML, que mandan sobre las del archivo."""
    tags = [
        ("title", track.title),
        ("artist", track.artist),
        ("album_artist", track.album_artist),
        ("album", track.album),
        ("genre", track.genre),
        ("composer", track.composer),
        ("date", str(track.year or "")),
        ("track", _fraction(track.track_number, track.track_count)),
        ("disc", _fraction(track.disc_number, track.disc_count)),
    ]
    return [(key, value) for key, value in tags if value]


def _fraction(number: Optional[int], total: Optional[int]) -> str:
    if not number:
        return ""
    return f"{number}/{total}" if total else str(number)


def build_ffmpeg_command(
    ffmpeg: str, track: Track, output: Path, quality: str, copy_audio: bool, with_cover: bool
) -> List[str]:
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
           "-i", str(track.source), "-map", "0:a:0"]
    if with_cover:
        cmd += ["-map", "0:v:0?", "-c:v", "copy", "-disposition:v:0", "attached_pic",
                "-metadata:s:v:0", "title=Album cover", "-metadata:s:v:0", "comment=Cover (front)"]
    if copy_audio:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "libmp3lame", *QUALITY_ARGS[quality]]
    # ID3v2.3 es la versión que entienden el Explorador de Windows y los coches.
    cmd += ["-map_metadata", "0", "-id3v2_version", "3", "-write_id3v1", "1"]
    # Etiquetas técnicas del contenedor MP4 que no pintan nada en un MP3.
    for key in ("major_brand", "minor_version", "compatible_brands"):
        cmd += ["-metadata", f"{key}="]
    for key, value in metadata_tags(track):
        cmd += ["-metadata", f"{key}={value}"]
    cmd += ["-f", "mp3", str(output)]
    return cmd


class Converter:
    def __init__(self, ffmpeg: str, quality: str, reencode_mp3: bool) -> None:
        self.ffmpeg = ffmpeg
        self.quality = quality
        self.reencode_mp3 = reencode_mp3

    def needs_encoder(self, jobs: Sequence[Job]) -> bool:
        return any(not self._copies_audio(track) for track, _ in jobs)

    def _copies_audio(self, track: Track) -> bool:
        return track.source is not None and track.source.suffix.lower() == ".mp3" and not self.reencode_mp3

    def __call__(self, track: Track, dest: Path) -> Result:
        copy_audio = self._copies_audio(track)
        tmp = dest.with_name(dest.name + ".part")
        error = ""
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Si la carátula da problemas, se repite sin ella.
            for with_cover in (True, False):
                cmd = build_ffmpeg_command(self.ffmpeg, track, tmp, self.quality, copy_audio, with_cover)
                proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE)
                if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 0:
                    os.replace(tmp, dest)
                    return Result(track, COPIED if copy_audio else CONVERTED, dest)
                error = _last_line(proc.stderr.decode("utf-8", "replace"))
        except OSError as exc:
            error = str(exc)
        finally:
            tmp.unlink(missing_ok=True)
        return Result(track, FAILED, dest, error or "ffmpeg falló sin dar detalles")


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def convert_all(
    jobs: Sequence[Job], converter: Callable[[Track, Path], Result], workers: int,
    on_result: Callable[[Result], None],
) -> List[Result]:
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(converter, track, dest) for track, dest in jobs]
        try:
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                on_result(result)
        except KeyboardInterrupt:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    return results


class Progress:
    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.width = len(str(total))

    def __call__(self, result: Result) -> None:
        self.done += 1
        line = f"[{self.done:>{self.width}}/{self.total}] {result.status}: {result.track.label}"
        if result.detail:
            line += f"  ({result.detail})"
        print(line, flush=True)


def find_ffmpeg(explicit: Optional[str]) -> str:
    if explicit:
        candidates = [explicit]
    else:
        local = Path(__file__).resolve().parent / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        candidates = ["ffmpeg", str(local), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    raise UserError(FFMPEG_HELP)


def ensure_mp3_encoder(ffmpeg: str) -> None:
    proc = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, errors="replace")
    if "libmp3lame" not in proc.stdout:
        raise UserError(f"El ffmpeg de {ffmpeg} no trae el codificador MP3 (libmp3lame). "
                        "Instala una versión completa de ffmpeg.")


# --- Informe ------------------------------------------------------------------

def write_report(path: Path, results: Sequence[Result]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(results, key=lambda r: (STATUS_ORDER.index(r.status), r.track.label.casefold()))
    # utf-8-sig para que Excel muestre bien los acentos.
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["estado", "artista", "álbum", "título", "archivo original", "mp3", "detalle"])
        for result in ordered:
            track = result.track
            writer.writerow([
                result.status,
                track.artist or track.album_artist,
                track.album,
                track.title or (track.source.stem if track.source else ""),
                str(track.source or ""),
                str(result.dest or ""),
                result.detail,
            ])


def print_summary(results: Sequence[Result], report: Path) -> None:
    counts = Counter(result.status for result in results)
    print("\nResumen:")
    for status in STATUS_ORDER:
        if counts[status]:
            print(f"  {status:<22}{counts[status]:>7}")
    if counts[PROTECTED]:
        print("\nLas canciones protegidas son de la suscripción de Apple Music: Apple las cifra\n"
              "y no se pueden pasar a MP3. Si quieres tenerlas en MP3, cómpralas en la\n"
              "iTunes Store (se venden sin DRM) y vuelve a ejecutar el programa.")
    if counts[NOT_DOWNLOADED]:
        print("\nHay canciones que solo están en la nube. Descárgalas en la app Música\n"
              "(clic derecho > Descargar) y vuelve a ejecutar el programa.")
    print(f"\nInforme completo: {report}")


# --- Interfaz -----------------------------------------------------------------

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="biblioteca_a_mp3",
        description="Convierte a MP3 las canciones sin DRM de tu biblioteca de Música/iTunes.",
        epilog=EXPORT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("origen", help="biblioteca exportada (.xml) o carpeta con canciones")
    parser.add_argument("-o", "--salida", default=str(DEFAULT_OUTPUT),
                        help="carpeta donde guardar los MP3 (por defecto: %(default)s)")
    parser.add_argument("-c", "--calidad", type=str.lower, choices=list(QUALITY_ARGS), default=DEFAULT_QUALITY,
                        help="kbps constantes, o v0/v2 para calidad variable (por defecto: %(default)s)")
    parser.add_argument("-l", "--lista", action="append", default=[], metavar="NOMBRE",
                        help="convertir solo esta lista de reproducción (repetible; solo con el .xml)")
    parser.add_argument("-j", "--hilos", type=int, default=max(1, min(4, os.cpu_count() or 1)),
                        help="conversiones a la vez (por defecto: %(default)s)")
    parser.add_argument("--sobrescribir", action="store_true",
                        help="volver a convertir aunque el MP3 ya exista")
    parser.add_argument("--recodificar-mp3", action="store_true",
                        help="recodificar también los que ya son MP3 (por defecto se copian sin pérdida)")
    parser.add_argument("--simulacion", action="store_true",
                        help="no convierte nada; solo genera el informe con lo que haría")
    parser.add_argument("--informe", help=f"ruta del informe CSV (por defecto: {REPORT_NAME} en la carpeta de salida)")
    parser.add_argument("--ffmpeg", help="ruta a ffmpeg si no está en el PATH")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.hilos < 1:
        parser.error("--hilos tiene que ser 1 o más")
    return args


def clean_user_path(raw: str) -> Path:
    """Arreglos para rutas arrastradas a la terminal (comillas, '\\ ')."""
    raw = raw.strip()
    if os.name == "nt":
        raw = raw.strip('"')
    else:
        try:
            parts = shlex.split(raw)
        except ValueError:
            parts = []
        if len(parts) == 1:
            raw = parts[0]
    return Path(raw).expanduser()


def interactive_args() -> List[str]:
    print(f"Biblioteca a MP3 {__version__}\n")
    print("Convierte a MP3 tus canciones sin DRM (compras de iTunes, CDs, archivos propios).")
    print("Las de la suscripción de Apple Music están cifradas por Apple: se detectan y se\n"
          "apuntan en el informe, pero no se pueden convertir.\n")
    print(EXPORT_HELP + "\n")
    while True:
        source = clean_user_path(input("Biblioteca (.xml) o carpeta:\n> "))
        if source.exists():
            break
        print(f"No encuentro {source}. Prueba otra vez.\n")
    raw_out = input(f"\nCarpeta donde guardar los MP3 [{DEFAULT_OUTPUT}]:\n> ")
    out_dir = clean_user_path(raw_out) if raw_out.strip() else DEFAULT_OUTPUT
    while True:
        quality = input(f"\nCalidad ({', '.join(QUALITY_ARGS)}) [{DEFAULT_QUALITY}]: ").strip().lower()
        quality = quality or DEFAULT_QUALITY
        if quality in QUALITY_ARGS:
            break
        print("Elige una de las opciones de la lista.")
    print()
    return [str(source), "--salida", str(out_dir), "--calidad", quality]


def run(args: argparse.Namespace) -> int:
    source = Path(args.origen).expanduser()
    out_dir = Path(args.salida).expanduser()
    report = Path(args.informe).expanduser() if args.informe else out_dir / REPORT_NAME
    ffmpeg = None if args.simulacion else find_ffmpeg(args.ffmpeg)

    if source.is_dir():
        if args.lista:
            raise UserError("--lista solo funciona con la biblioteca exportada (.xml), no con una carpeta.")
        print(f"Buscando canciones en {source} ...")
        tracks = scan_folder(source, exclude=out_dir)
    elif source.is_file():
        print(f"Leyendo la biblioteca {source} ...")
        tracks = load_library_xml(source, args.lista)
    else:
        raise UserError(f"No encuentro {source}")
    if not tracks:
        print("No he encontrado canciones.")
        return 0

    print(f"{_songs(len(tracks))}. Comprobando cuáles se pueden convertir ...")
    results, jobs = plan(tracks, out_dir, args.sobrescribir)
    if args.simulacion:
        results += [Result(track, SIMULATED, dest) for track, dest in jobs]
    elif jobs:
        converter = Converter(ffmpeg, args.calidad, args.recodificar_mp3)
        if converter.needs_encoder(jobs):
            ensure_mp3_encoder(ffmpeg)
        print(f"Convirtiendo {_songs(len(jobs))} a MP3 en {out_dir} ...\n")
        results += convert_all(jobs, converter, args.hilos, Progress(len(jobs)))
    else:
        print("No hay nada nuevo que convertir.")

    write_report(report, results)
    print_summary(results, report)
    return 1 if any(result.status == FAILED for result in results) else 0


def _songs(n: int) -> str:
    return "1 canción" if n == 1 else f"{n} canciones"


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _configure_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    interactive = not argv and sys.stdin.isatty()
    try:
        if interactive:
            argv = interactive_args()
        return run(parse_args(argv))
    except UserError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado. Si lo vuelves a ejecutar, las canciones ya convertidas se saltan.")
        return 130
    finally:
        if interactive:
            try:
                input("\nPulsa Intro para salir...")
            except (KeyboardInterrupt, EOFError):
                pass


if __name__ == "__main__":
    sys.exit(main())
