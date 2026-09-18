from __future__ import annotations

import base64
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .pdf_service import (
    MAX_UPLOAD_BYTES,
    PDFPreviewError,
    generate_test_pdf,
    normalize_missing_inks,
    render_pdf,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="CMYK Preview",
    description="Preview an approximation of a PDF printed with missing process inks.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/test-pdf")
def test_pdf(seed: int | None = None) -> Response:
    pdf = generate_test_pdf(seed)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="cmyk-printer-test.pdf"'},
    )


@app.post("/api/preview")
def preview_pdf(
    files: Annotated[list[UploadFile], File(alias="file")],
    missing_inks: Annotated[list[str], Form()],
) -> JSONResponse:
    try:
        if len(files) != 1:
            raise PDFPreviewError("Upload exactly one PDF document at a time.")
        file = files[0]
        normalized = normalize_missing_inks(missing_inks)
        # Read one extra byte so oversized files are rejected without retaining more
        # than the documented limit in memory.
        contents = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(contents) > MAX_UPLOAD_BYTES:
            raise PDFPreviewError(
                f"The PDF is too large. The maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            )
        pages = render_pdf(contents, normalized)
        return JSONResponse(
            {
                "filename": file.filename or "document.pdf",
                "missing_inks": list(normalized),
                "page_count": len(pages),
                "pages": [
                    {
                        "number": page.number,
                        "width": page.width,
                        "height": page.height,
                        "original_data_url": "data:image/png;base64,"
                        + base64.b64encode(page.original_png).decode("ascii"),
                        "data_url": "data:image/png;base64,"
                        + base64.b64encode(page.png).decode("ascii"),
                    }
                    for page in pages
                ],
            }
        )
    except PDFPreviewError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    finally:
        for uploaded_file in files:
            uploaded_file.file.close()
