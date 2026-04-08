# Python logic using pypdf to turn a PDF file into a clean string of text.
# logic to extract text from PDFs using PyMuPDF

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
from fastapi import UploadFile, HTTPException


ALLOWED_MIME_TYPES = {
    "application/pdf"  #pdf format only
}

MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


async def read_and_validate(file: UploadFile) -> bytes:
    """
    Read the uploaded file into memory and validate:
    - Content type is PDF or Word
    - File size is within the limit
    Returns raw bytes.
     {0s and 1s}
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. "
                   f"Only PDF files are accepted.",
        )

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File '{file.filename}' exceeds the {MAX_FILE_SIZE_MB}MB size limit.",
        )

    return contents


def extract_text(file_bytes: bytes, content_type: str) -> str:
    """
    Extract plain text from PDF bytes.
    Returns a single string of all extracted text.
    """
    print("content_type: ", content_type)
    return _extract_from_pdf(file_bytes)

def _extract_from_pdf(file_bytes: bytes) -> str:
    try:
        import pypdf
    except ImportError:
        raise RuntimeError(
            "pypdf is not installed. Add 'pypdf>=3.0.0' to requirements.txt"
        )
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))  # BytesIO is used to read the file in memory
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
    except:
        print("Error in PDF extraction")
        
    if not text:   # checks for photos or scanned page
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from the PDF. "
                   "The file may be scanned or image-based.",
        )

    return text
