import asyncio
import io
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import static_ffmpeg

# Ensure ffmpeg binaries from static-ffmpeg are registered in system PATH
static_ffmpeg.add_paths()

app = FastAPI(title="Multi-Utility Media Hub")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_home():
    return FileResponse("static/index.html")


# 1. Image Converter & Compressor
@app.post("/api/process-image")
async def process_image(
    file: UploadFile = File(...),
    target_format: str = Form("WEBP"),
    quality: int = Form(80),
):
    valid_formats = {"WEBP", "JPEG", "PNG"}
    target_format = target_format.upper()
    if target_format not in valid_formats:
        raise HTTPException(status_code=400, detail="Unsupported output format.")

    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))

        if target_format == "JPEG" and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        output_buffer = io.BytesIO()
        save_kwargs = {"format": target_format}
        if target_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = max(1, min(quality, 100))
            save_kwargs["optimize"] = True

        image.save(output_buffer, **save_kwargs)
        output_buffer.seek(0)

        base_name = os.path.splitext(file.filename)[0]
        ext = target_format.lower()
        output_filename = f"{base_name}_converted.{ext}"

        media_types = {
            "WEBP": "image/webp",
            "JPEG": "image/jpeg",
            "PNG": "image/png",
        }

        return StreamingResponse(
            output_buffer,
            media_type=media_types[target_format],
            headers={"Content-Disposition": f'attachment; filename="{output_filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")


# 2. Privacy Cleaner (EXIF / Metadata Stripper)
@app.post("/api/strip-metadata")
async def strip_metadata(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))

        # Re-create image buffer without copying EXIF tags
        clean_image = Image.new(image.mode, image.size)
        clean_image.putdata(list(image.getdata()))

        output_buffer = io.BytesIO()
        save_format = image.format if image.format else "PNG"
        clean_image.save(output_buffer, format=save_format)
        output_buffer.seek(0)

        base_name = os.path.splitext(file.filename)[0]
        ext = save_format.lower()
        output_filename = f"{base_name}_clean.{ext}"

        return StreamingResponse(
            output_buffer,
            media_type=f"image/{ext}",
            headers={"Content-Disposition": f'attachment; filename="{output_filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metadata stripping failed: {str(e)}")


# 3. Fast Asynchronous Audio Converter (Direct FFmpeg Subprocess)
@app.post("/api/convert-audio")
async def convert_audio(
    file: UploadFile = File(...),
    target_format: str = Form("mp3"),
    bitrate: str = Form("192k"),
):
    target_format = target_format.lower()
    valid_formats = {"mp3", "wav", "ogg"}
    if target_format not in valid_formats:
        raise HTTPException(status_code=400, detail="Unsupported audio format.")

    # Create temporary scratch directory to avoid PCM in-memory expansion
    with tempfile.TemporaryDirectory() as tmpdir:
        safe_filename = Path(file.filename).name
        input_path = Path(tmpdir) / safe_filename
        output_filename = f"{Path(safe_filename).stem}_converted.{target_format}"
        output_path = Path(tmpdir) / output_filename

        # Stream upload directly to disk
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Build FFmpeg command
        cmd = ["ffmpeg", "-y", "-i", str(input_path)]

        if target_format in ("mp3", "ogg"):
            cmd += ["-b:a", bitrate, "-threads", "1"]
        elif target_format == "wav":
            cmd += ["-acodec", "pcm_s16le"]

        cmd.append(str(output_path))

        # Run native FFmpeg asynchronously
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode(errors="replace")[:300]
            raise HTTPException(status_code=500, detail=f"FFmpeg conversion failed: {error_msg}")

        with open(output_path, "rb") as f:
            data = f.read()

        media_types = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "ogg": "audio/ogg",
        }

        return StreamingResponse(
            io.BytesIO(data),
            media_type=media_types[target_format],
            headers={"Content-Disposition": f'attachment; filename="{output_filename}"'},
        )