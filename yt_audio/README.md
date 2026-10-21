# Descargador de audio de YouTube a MP3 (para datasets)

Script en Python basado en [yt-dlp](https://github.com/yt-dlp/yt-dlp) que descarga el audio
de vídeos (o listas de reproducción) en MP3 y genera un `metadatos.csv` con el origen
de cada pista, útil para documentar un dataset de entrenamiento.

## Requisitos

- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) instalado y en el PATH
- `pip install -r requirements.txt`

## Uso

```bash
# Un vídeo
python descargar_audio.py "https://www.youtube.com/watch?v=XXXX"

# Varias URLs desde un archivo (una por línea, # para comentarios)
python descargar_audio.py --lista urls.txt -o dataset

# Solo vídeos con licencia Creative Commons, en mono 16 kHz (típico para modelos de voz)
python descargar_audio.py --lista urls.txt --solo-cc --mono-16k
```

Resultado en la carpeta de salida:

- `<id>.mp3` — un archivo por vídeo
- `metadatos.csv` — id, título, autor, licencia, duración, URL y archivo
- `.descargados.txt` — registro para no volver a descargar lo mismo

## Nota sobre derechos

Descargar contenido de YouTube puede ir contra sus Términos de Servicio y el audio suele
estar protegido por derechos de autor. Para un proyecto de clase lo más seguro es usar
vídeos con licencia Creative Commons (`--solo-cc`), contenido propio o con permiso del autor,
y conservar el `metadatos.csv` para poder citar las fuentes.
