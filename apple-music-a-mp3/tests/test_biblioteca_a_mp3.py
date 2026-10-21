import contextlib
import csv
import io
import json
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import biblioteca_a_mp3 as app  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def box(box_type: bytes, body: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(body), box_type) + body


def fake_mp4(sample_entry: bytes) -> bytes:
    """MP4 mínimo con una pista cuyo stsd tiene la entrada indicada."""
    stsd = box(b"stsd", b"\x00\x00\x00\x00" + struct.pack(">I", 1) + box(sample_entry, b"\x00" * 28))
    trak = box(b"trak", box(b"mdia", box(b"minf", box(b"stbl", stsd))))
    return box(b"ftyp", b"M4A \x00\x00\x02\x00") + box(b"moov", box(b"mvhd", b"\x00" * 100) + trak)


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


class SafeNameTests(unittest.TestCase):
    def test_replaces_invalid_characters(self):
        self.assertEqual(app.safe_name('AC/DC: "Live"?'), "AC_DC_ _Live__")

    def test_trims_trailing_dots_and_spaces(self):
        self.assertEqual(app.safe_name("  Hola...  "), "Hola")

    def test_hidden_and_reserved_names_get_prefix(self):
        self.assertEqual(app.safe_name("...And Justice for All"), "_...And Justice for All")
        self.assertEqual(app.safe_name("con"), "_con")
        self.assertEqual(app.safe_name("NUL.txt"), "_NUL.txt")

    def test_empty_and_long_names(self):
        self.assertEqual(app.safe_name("   "), "_")
        self.assertEqual(len(app.safe_name("x" * 500)), 120)


class FileUrlTests(unittest.TestCase):
    def test_mac_url(self):
        url = "file:///Users/ana/Music/Music/Media.localized/Music/Ros%C3%A9/Album/01%20Canci%C3%B3n.m4a"
        self.assertEqual(app.file_url_to_path(url).as_posix(),
                         "/Users/ana/Music/Music/Media.localized/Music/Rosé/Album/01 Canción.m4a")

    def test_windows_url(self):
        url = "file://localhost/C:/Users/Ana/Music/iTunes/01%20Song.m4a"
        self.assertEqual(app.file_url_to_path(url).as_posix(), "C:/Users/Ana/Music/iTunes/01 Song.m4a")

    def test_network_share(self):
        self.assertEqual(app.file_url_to_path("file://nas/musica/a.mp3").as_posix(), "//nas/musica/a.mp3")

    def test_non_file_url(self):
        self.assertIsNone(app.file_url_to_path("http://example.com/stream"))


class DrmDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name: str, data: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def test_plain_aac_is_not_protected(self):
        self.assertFalse(app.is_drm_protected(self.write("a.m4a", fake_mp4(b"mp4a"))))

    def test_fairplay_entries_are_protected(self):
        for entry in (b"drms", b"enca"):
            with self.subTest(entry=entry):
                self.assertTrue(app.is_drm_protected(self.write("a.m4a", fake_mp4(entry))))

    def test_m4p_extension_is_protected(self):
        self.assertTrue(app.is_drm_protected(self.write("a.m4p", b"")))

    def test_garbage_and_other_formats(self):
        self.assertFalse(app.is_drm_protected(self.write("a.m4a", b"\x00\x00\x00\x01moov")))
        self.assertFalse(app.is_drm_protected(self.write("a.mp3", b"ID3")))


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.song = self.tmp / "Media" / "01 Canción.m4a"
        self.song.parent.mkdir()
        self.song.write_bytes(fake_mp4(b"mp4a"))
        self.drm = self.tmp / "Media" / "02 Cifrada.m4a"
        self.drm.write_bytes(fake_mp4(b"enca"))

    def write_library(self, tracks: dict, playlists: list = ()) -> Path:
        path = self.tmp / "Biblioteca.xml"
        with open(path, "wb") as fh:
            plistlib.dump({"Tracks": tracks, "Playlists": list(playlists)}, fh)
        return path

    def library(self) -> Path:
        return self.write_library(
            {
                "1": {"Track ID": 1, "Name": "Canción", "Artist": "Rosé", "Album": "Disco",
                      "Track Number": 1, "Track Count": 10, "Disc Number": 2, "Disc Count": 2,
                      "Year": 2020, "Location": file_url(self.song)},
                "2": {"Track ID": 2, "Name": "Cifrada", "Artist": "Otro", "Location": file_url(self.drm)},
                "3": {"Track ID": 3, "Name": "Streaming", "Artist": "X", "Apple Music": True},
                "4": {"Track ID": 4, "Name": "Comprada", "Artist": "Y", "Purchased": True, "Apple Music": True},
                "5": {"Track ID": 5, "Name": "Borrada", "Location": "file:///no/existe.m4a"},
                "6": {"Track ID": 6, "Name": "Vídeo", "Has Video": True, "Location": file_url(self.song)},
                "7": {"Track ID": 7, "Name": "Radio", "Track Type": "URL", "Location": "http://radio"},
                "8": {"Track ID": 8, "Name": "Marcada", "Protected": True, "Location": file_url(self.song)},
            },
            [{"Name": "Favoritas", "Playlist Items": [{"Track ID": 2}, {"Track ID": 1}, {"Track ID": 1}]}],
        )

    def test_loads_audio_tracks_only(self):
        tracks = app.load_library_xml(self.library())
        self.assertEqual([t.title for t in tracks],
                         ["Canción", "Cifrada", "Streaming", "Comprada", "Borrada", "Marcada"])
        first = tracks[0]
        self.assertEqual(first.source, self.song.resolve())
        self.assertEqual((first.year, first.disc_number, first.disc_count), (2020, 2, 2))

    def test_playlist_filter_keeps_order_without_duplicates(self):
        tracks = app.load_library_xml(self.library(), ["favoritas"])
        self.assertEqual([t.title for t in tracks], ["Cifrada", "Canción"])

    def test_unknown_playlist_is_an_error(self):
        with self.assertRaisesRegex(app.UserError, "Gimnasio"):
            app.load_library_xml(self.library(), ["Gimnasio"])

    def test_not_a_library(self):
        path = self.tmp / "otro.xml"
        path.write_text("<html></html>")
        with self.assertRaises(app.UserError):
            app.load_library_xml(path)

    def test_plan_classifies_every_track(self):
        tracks = app.load_library_xml(self.library())
        skipped, jobs = app.plan(tracks, self.tmp / "out", overwrite=False)
        statuses = {r.track.title: r.status for r in skipped}
        self.assertEqual(statuses, {
            "Cifrada": app.PROTECTED,
            "Streaming": app.PROTECTED,
            "Comprada": app.NOT_DOWNLOADED,
            "Borrada": app.MISSING,
            "Marcada": app.PROTECTED,
        })
        self.assertEqual(len(jobs), 1)
        track, dest = jobs[0]
        self.assertEqual(dest, self.tmp / "out" / "Rosé" / "Disco" / "2-01 Canción.mp3")

    def test_plan_skips_existing_and_deduplicates_names(self):
        twin = app.Track(source=self.song, title="Canción", artist="Rosé", album="Disco")
        existing = self.tmp / "out" / "Rosé" / "Disco" / "Canción.mp3"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"")
        skipped, jobs = app.plan([twin, twin], self.tmp / "out", overwrite=False)
        self.assertEqual([r.status for r in skipped], [app.EXISTS])
        self.assertEqual([d.name for _, d in jobs], ["Canción (2).mp3"])

    def test_compilation_and_unknown_folders(self):
        comp = app.Track(source=None, title="T", artist="A", compilation=True)
        self.assertEqual(app.destination_for(comp), Path("Varios artistas", "Álbum desconocido", "T.mp3"))
        bare = app.Track(source=Path("/x/pista.wav"))
        self.assertEqual(app.destination_for(bare), Path("Artista desconocido", "Álbum desconocido", "pista.mp3"))


class FolderTests(unittest.TestCase):
    def test_scan_mirrors_structure_and_skips_output(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        (root / "Artista" / "Álbum").mkdir(parents=True)
        (root / "Artista" / "Álbum" / "01 Tema.m4a").write_bytes(b"")
        (root / "Artista" / "Álbum" / "._01 Tema.m4a").write_bytes(b"")
        (root / "Artista" / "Álbum" / "portada.jpg").write_bytes(b"")
        (root / "MP3").mkdir()
        (root / "MP3" / "viejo.mp3").write_bytes(b"")
        tracks = app.scan_folder(root, exclude=root / "MP3")
        self.assertEqual([app.destination_for(t) for t in tracks], [Path("Artista", "Álbum", "01 Tema.mp3")])


class CleanUserPathTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "rutas de Mac/Linux")
    def test_dragged_paths(self):
        self.assertEqual(app.clean_user_path("/Users/ana/Mi\\ Música/b.xml "), Path("/Users/ana/Mi Música/b.xml"))
        self.assertEqual(app.clean_user_path("'/Users/ana/Mi Música/b.xml'"), Path("/Users/ana/Mi Música/b.xml"))
        self.assertEqual(app.clean_user_path("/Users/ana/Mi Música/b.xml"), Path("/Users/ana/Mi Música/b.xml"))


@unittest.skipUnless(FFMPEG and FFPROBE, "hace falta ffmpeg")
class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        media = self.tmp / "Media"
        media.mkdir()
        cover = self.tmp / "cover.png"
        self.ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", str(cover))
        self.song = media / "01 Canción.m4a"
        self.ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-i", str(cover),
                    "-map", "0", "-map", "1", "-c:a", "aac", "-c:v", "copy", "-disposition:v", "attached_pic",
                    "-metadata", "title=Título del archivo", "-metadata", "artist=Rosé", str(self.song))
        self.old_mp3 = media / "02 Viejo.mp3"
        self.ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=1", "-c:a", "libmp3lame",
                    "-metadata", "title=Viejo", str(self.old_mp3))
        # Copia "cifrada": misma canción con la entrada mp4a cambiada a enca.
        self.drm = media / "03 Cifrada.m4a"
        self.drm.write_bytes(self.song.read_bytes().replace(b"mp4a", b"enca", 1))
        self.library = self.tmp / "Biblioteca.xml"
        with open(self.library, "wb") as fh:
            plistlib.dump({"Tracks": {
                "1": {"Name": "Canción", "Artist": "Rosé", "Album": "Disco", "Year": 2021,
                      "Track Number": 1, "Track Count": 9, "Location": file_url(self.song)},
                "2": {"Name": "Viejo", "Artist": "Grupo", "Album": "Demo", "Location": file_url(self.old_mp3)},
                "3": {"Name": "Cifrada", "Artist": "Otro", "Album": "Nuevo", "Location": file_url(self.drm)},
                "4": {"Name": "Streaming", "Artist": "X", "Apple Music": True},
            }}, fh)

    def ffmpeg(self, *args):
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)

    def probe(self, path: Path) -> dict:
        out = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                             check=True, capture_output=True, text=True).stdout
        return json.loads(out)

    def run_main(self, *extra):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            code = app.main([str(self.library), "-o", str(self.tmp / "out"), *extra])
        return code, stdout.getvalue()

    def test_end_to_end(self):
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

        converted = self.tmp / "out" / "Rosé" / "Disco" / "01 Canción.mp3"
        info = self.probe(converted)
        audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
        covers = [s for s in info["streams"] if s["codec_type"] == "video"]
        self.assertEqual(audio[0]["codec_name"], "mp3")
        self.assertEqual(int(audio[0]["bit_rate"]), 320000)
        self.assertEqual(covers[0]["disposition"]["attached_pic"], 1)
        tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
        self.assertEqual(tags["title"], "Canción")  # el XML manda sobre el archivo
        self.assertEqual(tags["artist"], "Rosé")
        self.assertEqual(tags["album"], "Disco")
        self.assertEqual(tags["track"], "1/9")
        self.assertNotIn("major_brand", tags)

        copied = self.tmp / "out" / "Grupo" / "Demo" / "Viejo.mp3"
        self.assertEqual(self.probe(copied)["streams"][0]["codec_name"], "mp3")
        self.assertFalse((self.tmp / "out" / "Otro").exists())
        self.assertEqual(list((self.tmp / "out").rglob("*.part")), [])

        with open(self.tmp / "out" / app.REPORT_NAME, encoding="utf-8-sig") as fh:
            rows = {row["título"]: row["estado"] for row in csv.DictReader(fh)}
        self.assertEqual(rows, {"Canción": app.CONVERTED, "Viejo": app.COPIED,
                                "Cifrada": app.PROTECTED, "Streaming": app.PROTECTED})

        # La segunda vez no repite trabajo.
        code, output = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("No hay nada nuevo que convertir", output)

    def test_simulation_writes_nothing_but_the_report(self):
        code, _ = self.run_main("--simulacion")
        self.assertEqual(code, 0)
        self.assertEqual([p.name for p in (self.tmp / "out").iterdir()], [app.REPORT_NAME])

    def test_folder_mode_and_vbr(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = app.main([str(self.tmp / "Media"), "-o", str(self.tmp / "out"), "-c", "V0"])
        self.assertEqual(code, 0, stdout.getvalue())
        names = sorted(p.name for p in (self.tmp / "out").glob("*.mp3"))
        self.assertEqual(names, ["01 Canción.mp3", "02 Viejo.mp3"])
        tags = {k.lower(): v for k, v in self.probe(self.tmp / "out" / "01 Canción.mp3")["format"]["tags"].items()}
        self.assertEqual(tags["title"], "Título del archivo")  # sin XML se conservan las del archivo

    def test_broken_file_is_reported_as_error(self):
        self.song.write_bytes(b"esto no es audio")
        code, output = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn(app.FAILED, output)
        self.assertEqual(list((self.tmp / "out").rglob("*.part")), [])


if __name__ == "__main__":
    unittest.main()
