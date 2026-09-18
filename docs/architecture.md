# Architecture

CMYK Preview is intentionally small:

1. FastAPI serves the static interface and accepts one multipart PDF upload.
2. PyMuPDF rasterizes each page into CMYK at a bounded display resolution.
3. Pillow clears the selected C, M, Y, and/or K channels and converts both original and simulated pages to PNG.
4. FastAPI returns data URLs for both versions of every page.
5. The browser builds a labeled original/simulation comparison for each page.

The service keeps uploaded bytes and rendered images in request memory only. It has a 100 MB upload limit and intentionally does not impose a page-count limit.
