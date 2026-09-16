from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import io
import os

app = FastAPI(title="Media Converter & Compressor")

# Mount the frontend directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_home():
    return FileResponse("static/index.html")

@app.post("/api/process-image")
async def process_image(
    file: UploadFile = File(...),
    target_format: str = Form("WEBP"),   # Options: WEBP, JPEG, PNG
    quality: int = Form(80)              # Compression level (1-100)
):
    valid_formats = {"WEBP", "JPEG", "PNG"}
    target_format = target_format.upper()
    if target_format not in valid_formats:
        raise HTTPException(status_code=400, detail="Unsupported output format.")

    try:
        # Read file directly into RAM
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))

        # Convert RGBA to RGB if saving to JPEG
        if target_format == "JPEG" and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        # Save processed file into an in-memory buffer
        output_buffer = io.BytesIO()
        save_kwargs = {"format": target_format}
        if target_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = max(1, min(quality, 100))
            save_kwargs["optimize"] = True

        image.save(output_buffer, **save_kwargs)
        output_buffer.seek(0)

        # Output filename setup
        base_name = os.path.splitext(file.filename)[0]
        ext = target_format.lower()
        output_filename = f"{base_name}_compressed.{ext}"

        media_types = {
            "WEBP": "image/webp",
            "JPEG": "image/jpeg",
            "PNG": "image/png"
        }

        return StreamingResponse(
            output_buffer,
            media_type=media_types[target_format],
            headers={"Content-Disposition": f'attachment; filename="{output_filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")