# Biblioteca a MP3

Convierte a `.mp3` las canciones de tu biblioteca de la app **Música** (Apple Music) o de **iTunes** que tengas guardadas en tu equipo, conservando etiquetas (título, artista, álbum, año, número de pista) y carátula.

## Qué se puede convertir y qué no

| Tipo de canción | ¿Se convierte? |
| --- | --- |
| Compradas en la iTunes Store (desde 2009 se venden sin DRM) | ✅ Sí (si están descargadas) |
| Importadas de CDs | ✅ Sí |
| Archivos que añadiste tú (m4a, wav, aiff, flac, mp3…) | ✅ Sí (los MP3 se copian sin perder calidad) |
| De la **suscripción de Apple Music** | ❌ No |

Apple cifra las canciones de la suscripción con su DRM FairPlay (archivos `.m4p`). Son un alquiler ligado a tu cuenta y quitarles esa protección no es legal ni lo permiten las condiciones de Apple. El programa las detecta, no las toca y las apunta en el informe para que sepas cuáles son. Si quieres alguna en MP3, cómprala en la iTunes Store y vuelve a ejecutar el programa.

## Qué necesitas

1. **Python 3.9 o superior**: <https://www.python.org/downloads/> (en Mac suele venir ya instalado).
2. **ffmpeg**, que es el que hace la conversión:
   - Mac: `brew install ffmpeg` (si no tienes Homebrew: <https://brew.sh>)
   - Windows: `winget install ffmpeg`, o copia `ffmpeg.exe` en esta misma carpeta
   - Linux: `sudo apt install ffmpeg`

## Cómo usarlo

### 1. Exporta tu biblioteca

- **Mac (app Música)**: `Archivo > Biblioteca > Exportar biblioteca…` y guarda el `.xml`.
- **Windows (iTunes)**: `Archivo > Biblioteca > Exportar biblioteca…`

Si tu app no tiene esa opción, puedes usar directamente la carpeta donde están las canciones (en Mac suele ser `~/Música/Music/Media`).

Antes de exportar, descarga en la app las compras que solo estén en la nube (clic derecho > **Descargar**); si no, aparecerán como «no descargada».

### 2. Ejecuta el programa

- **Mac**: doble clic en `Convertir a MP3.command`.
- **Windows**: doble clic en `Convertir a MP3.bat`.

Te pedirá que arrastres el `.xml` (o la carpeta), dónde guardar los MP3 y la calidad. Al terminar verás un resumen y se crea `informe-mp3.csv` (se abre con Excel o Numbers) con el estado de cada canción.

> En Mac, si al hacer doble clic dice que no se puede abrir, haz clic derecho > **Abrir**. Si dice que no tiene permisos, ejecuta en el Terminal `chmod +x "Convertir a MP3.command"`.

### Desde la terminal

```bash
# Toda la biblioteca, a 320 kbps, en ~/Music/MP3
python3 biblioteca_a_mp3.py ~/Desktop/Biblioteca.xml

# Solo algunas listas de reproducción, en otra carpeta
python3 biblioteca_a_mp3.py Biblioteca.xml -o /Volumes/USB/Musica -l "Coche" -l "Favoritas"

# Una carpeta con canciones, en calidad variable (V0)
python3 biblioteca_a_mp3.py ~/Music/Music/Media -c v0

# Ver qué haría sin convertir nada (solo genera el informe)
python3 biblioteca_a_mp3.py Biblioteca.xml --simulacion
```

| Opción | Para qué sirve |
| --- | --- |
| `-o`, `--salida` | Carpeta de destino (por defecto `~/Music/MP3`) |
| `-c`, `--calidad` | `320` (por defecto), `256`, `192`, `128`, `v0`, `v2` |
| `-l`, `--lista` | Convertir solo esa lista de reproducción (se puede repetir; solo con el `.xml`) |
| `-j`, `--hilos` | Cuántas canciones convertir a la vez |
| `--sobrescribir` | Volver a convertir aunque el MP3 ya exista |
| `--recodificar-mp3` | Recodificar también las que ya son MP3 (por defecto se copian tal cual) |
| `--simulacion` | No convierte nada; solo genera el informe |
| `--informe` | Dónde guardar el informe CSV |
| `--ffmpeg` | Ruta a ffmpeg si no está en el PATH |

## Cómo quedan los archivos

Con el `.xml`, los MP3 se ordenan como en la app: `Artista/Álbum/01 Título.mp3` (los discos múltiples quedan como `2-01 Título.mp3` y los recopilatorios en `Varios artistas`). Las etiquetas salen de tu biblioteca, así que se respetan los cambios que hayas hecho en la app. Con una carpeta, se copia la misma estructura de subcarpetas.

Puedes cortarlo cuando quieras (Ctrl+C) y volver a lanzarlo: las canciones que ya estén convertidas se saltan.

## Alternativa sin instalar nada

La propia app Música puede crear copias MP3 de canciones sin DRM, una selección cada vez: en `Música > Ajustes > Archivos > Ajustes de importación` elige **Codificador MP3**, selecciona las canciones y ve a `Archivo > Convertir > Crear versión MP3`. Las copias quedan dentro de la biblioteca, mezcladas con los originales; este programa las saca a una carpeta aparte, ordenadas y con informe.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
