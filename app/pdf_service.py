from __future__ import annotations

import io
import itertools
import random
from dataclasses import dataclass
from typing import Iterable

import fitz
from PIL import Image, ImageChops, ImageMath
from reportlab.lib.colors import CMYKColor, Color, HexColor, black, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen.canvas import Canvas

INKS = ("cyan", "magenta", "yellow", "black")
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
RENDER_DPI = 120
MAX_RENDER_EDGE = 1800


class PDFPreviewError(ValueError):
    """A safe, user-facing PDF processing error."""


@dataclass(frozen=True)
class RenderedPage:
    number: int
    width: int
    height: int
    original_png: bytes
    png: bytes


def normalize_missing_inks(values: Iterable[str]) -> tuple[str, ...]:
    """Normalize repeated or comma-delimited form values into a stable ink tuple."""
    result: list[str] = []
    for value in values:
        for candidate in value.split(","):
            ink = candidate.strip().lower()
            if not ink:
                continue
            if ink not in INKS:
                raise PDFPreviewError(f"Unknown ink color: {candidate.strip()}")
            if ink not in result:
                result.append(ink)
    if not result:
        raise PDFPreviewError("Select at least one missing ink color.")
    return tuple(result)


def remove_inks(image: Image.Image, missing_inks: Iterable[str]) -> Image.Image:
    """Approximate missing printer inks by zeroing channels in CMYK color space."""
    missing = normalize_missing_inks(missing_inks)

    # Preserve true process separations when the renderer or caller provides
    # native CMYK pixels. This is more faithful than reconstructing channels.
    if image.mode == "CMYK":
        channels = list(image.split())
        blank = Image.new("L", image.size, 0)
        for ink in missing:
            channels[INKS.index(ink)] = blank
        return Image.merge("CMYK", channels).convert("RGB")

    rgb = image.convert("RGB")

    # Pillow's direct RGB -> CMYK conversion represents black as equal C/M/Y
    # and leaves K empty. Use the standard under-color-removal formula instead,
    # so disabling black produces the behavior a printer user expects.
    red, green, blue = rgb.split()
    maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    key = ImageChops.invert(maximum)

    def separate(component: Image.Image) -> Image.Image:
        return ImageMath.unsafe_eval(
            'convert((maximum - component) * 255 / max(maximum, 1), "L")',
            maximum=maximum,
            component=component,
        )

    channels = [separate(red), separate(green), separate(blue), key]
    blank = Image.new("L", rgb.size, 0)
    for ink in missing:
        channels[INKS.index(ink)] = blank

    cyan, magenta, yellow, key = channels

    def combine(component: Image.Image) -> Image.Image:
        return ImageMath.unsafe_eval(
            'convert((255 - component) * (255 - key) / 255, "L")',
            component=component,
            key=key,
        )

    return Image.merge("RGB", (combine(cyan), combine(magenta), combine(yellow)))


def _open_pdf(pdf_bytes: bytes) -> fitz.Document:
    if not pdf_bytes:
        raise PDFPreviewError("The uploaded file is empty.")
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise PDFPreviewError(
            f"The PDF is too large. The maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    # This gives fast, clear feedback for common non-PDF uploads. Fitz remains the
    # authority because whitespace and binary comments may legally occur later.
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise PDFPreviewError("The uploaded file is not a valid PDF.")
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFPreviewError("The PDF is damaged or could not be read.") from exc
    if document.needs_pass:
        document.close()
        raise PDFPreviewError("Password-protected PDFs are not supported.")
    if document.page_count == 0:
        document.close()
        raise PDFPreviewError("The PDF does not contain any pages.")
    return document


def render_pdf(pdf_bytes: bytes, missing_inks: Iterable[str]) -> list[RenderedPage]:
    missing = normalize_missing_inks(missing_inks)
    document = _open_pdf(pdf_bytes)
    pages: list[RenderedPage] = []
    try:
        base_zoom = RENDER_DPI / 72
        for index, page in enumerate(document):
            rect = page.rect
            longest_at_dpi = max(rect.width, rect.height) * base_zoom
            zoom = base_zoom * min(1.0, MAX_RENDER_EDGE / max(longest_at_dpi, 1))
            # Ask MuPDF for process separations so native CMYK content keeps its
            # original channel assignments. RGB and other spaces are converted by
            # MuPDF's color-managed renderer before simulation.
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csCMYK, alpha=False
            )
            image = Image.frombytes("CMYK", (pixmap.width, pixmap.height), pixmap.samples)
            original = image.convert("RGB")
            simulated = remove_inks(image, missing)
            original_output = io.BytesIO()
            original.save(original_output, "PNG", optimize=True)
            output = io.BytesIO()
            simulated.save(output, "PNG", optimize=True)
            pages.append(
                RenderedPage(
                    number=index + 1,
                    width=simulated.width,
                    height=simulated.height,
                    original_png=original_output.getvalue(),
                    png=output.getvalue(),
                )
            )
    except PDFPreviewError:
        raise
    except Exception as exc:
        raise PDFPreviewError("A page in this PDF could not be rendered.") from exc
    finally:
        document.close()
    return pages


def all_missing_ink_combinations() -> tuple[tuple[str, ...], ...]:
    return tuple(
        combination
        for length in range(1, len(INKS) + 1)
        for combination in itertools.combinations(INKS, length)
    )


def generate_test_pdf(seed: int | None = None) -> bytes:
    """Create a two-page diagnostic PDF with known CMYK and random RGB artwork."""
    rng = random.Random(seed)
    output = io.BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    canvas.setTitle("CMYK Preview Printer Test")
    canvas.setAuthor("CMYK Preview")

    canvas.setFillColor(white)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(black)
    canvas.setFont("Helvetica-Bold", 24)
    canvas.drawString(40, height - 45, "CMYK Printer Test")
    canvas.setFont("Helvetica", 10)
    canvas.drawString(
        40,
        height - 63,
        "Pure process inks, combinations, tints, and neutral registration",
    )

    swatches = [
        ("Cyan", CMYKColor(100, 0, 0, 0)),
        ("Magenta", CMYKColor(0, 100, 0, 0)),
        ("Yellow", CMYKColor(0, 0, 100, 0)),
        ("Black", CMYKColor(0, 0, 0, 100)),
        ("C + M", CMYKColor(100, 100, 0, 0)),
        ("M + Y", CMYKColor(0, 100, 100, 0)),
        ("C + Y", CMYKColor(100, 0, 100, 0)),
        ("Rich black", CMYKColor(60, 40, 40, 100)),
    ]
    swatch_w, swatch_h, gap = 175, 72, 14
    start_y = height - 165
    for index, (label, color) in enumerate(swatches):
        column, row = index % 4, index // 4
        x = 40 + column * (swatch_w + gap)
        y = start_y - row * 112
        canvas.setFillColor(color)
        canvas.rect(x, y, swatch_w, swatch_h, fill=1, stroke=0)
        canvas.setFillColor(black)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(x, y - 16, label)

    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(40, 255, "Process ink tint ramps")
    ramp_y = 210
    ramp_colors = [
        ("C", (1, 0, 0, 0)),
        ("M", (0, 1, 0, 0)),
        ("Y", (0, 0, 1, 0)),
        ("K", (0, 0, 0, 1)),
    ]
    for row, (label, components) in enumerate(ramp_colors):
        y = ramp_y - row * 38
        canvas.setFillColor(black)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(40, y + 8, label)
        for level in range(1, 11):
            amount = level / 10
            c, m, yy, k = (component * amount * 100 for component in components)
            canvas.setFillColor(CMYKColor(c, m, yy, k))
            canvas.rect(65 + (level - 1) * 68, y, 62, 25, fill=1, stroke=0)
    canvas.showPage()

    canvas.setFillColor(HexColor("#f6f4ef"))
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(black)
    canvas.setFont("Helvetica-Bold", 22)
    canvas.drawString(
        40,
        height - 45,
        f"Random mixed-color artwork — sample {rng.randrange(100000, 999999)}",
    )
    canvas.setFont("Helvetica", 10)
    canvas.drawString(
        40,
        height - 62,
        "Use this page to inspect interactions between missing process inks.",
    )
    for _ in range(55):
        x = rng.uniform(25, width - 100)
        y = rng.uniform(35, height - 125)
        shape_w = rng.uniform(25, 130)
        shape_h = rng.uniform(18, 100)
        canvas.setFillColor(
            Color(
                rng.random(),
                rng.random(),
                rng.random(),
                alpha=rng.uniform(0.45, 0.95),
            )
        )
        if rng.choice((True, False)):
            canvas.roundRect(x, y, shape_w, shape_h, rng.uniform(2, 18), fill=1, stroke=0)
        else:
            canvas.ellipse(x, y, x + shape_w, y + shape_h, fill=1, stroke=0)
    canvas.setFillColor(black)
    canvas.setFont("Helvetica", 12)
    canvas.drawString(40, 22, "Generated locally by CMYK Preview • no upload required")
    canvas.save()
    return output.getvalue()
