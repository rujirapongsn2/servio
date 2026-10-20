# Read scanned PDFs with local OCR

Rebuild the backend with `./services.sh rebuild backend`. The backend image includes Poppler and Tesseract with Thai and English languages. No OCR cloud account or embedding service changes are needed.

For a backend run outside Docker, install Poppler, Tesseract, and the Thai and English language data. Check `pdftoppm -v` and `tesseract --list-langs`. The language list must contain `tha` and `eng`.

Upload the original scanned PDF through Local Knowledge. Preview shows a warning identifying pages processed with OCR. Inspect the recognized text before accepting the import. Existing knowledge needs the original PDF uploaded again. Re-indexing stored text does not run OCR.

## Extraction behavior

Readable native text keeps its original page markers. Image-only pages and pages with fewer than 80 alphanumeric native characters plus image objects, including inline images and annotation appearance streams, use OCR. Pages whose native text extraction fails also use OCR. Native headers absent from OCR output are retained. Only entirely white rendered pages are omitted without changing later page numbers.

A failed render, missing language, timeout, or nonblank page without recognized text fails that PDF. A batch can still import other files and displays the failed filename, page, and cause as a warning. No digital-only partial version of a failed mixed PDF is imported.

## Limits

Each PDF accepts at most 200 pages and 2 million extracted characters. Rendering uses a grayscale raster with a 2400-pixel long edge. Each render has a 30-second timeout. Each Tesseract command has a 60-second timeout. OCR commands and queue wait share a 300-second deadline per PDF. One OCR command sequence runs at a time per backend worker, with one OpenMP thread. Multiple backend workers multiply this limit.

Temporary files are removed after each page. Native PDF parsing and native text extraction run inside the backend process outside the OCR deadline. Raster dimensions limit the output file, not Poppler decode memory. Deploy with container memory limits and keep worker count low on shared machines.

Pages containing substantial native text and an embedded scan retain native text without OCR. OCR does not reconstruct table structure, handwriting, or guaranteed reading order. Low-resolution, rotated, or noisy scans need review. This feature preserves page markers; clickable page citations are separate work.
