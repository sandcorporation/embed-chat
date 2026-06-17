"""CPU-compatible OCR service using EasyOCR backend.

Exposes the same /health and /ocr endpoints as the PaddleOCR service
so the backend ImageIngester can call either interchangeably.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Dict

import numpy as np
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel

app = FastAPI(title="OCR Service (EasyOCR)", version="1.0.0")

import easyocr
OCR = easyocr.Reader(["en", "ko"], gpu=False)


class OcrRequest(BaseModel):
    image_b64: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr")
def ocr(req: OcrRequest) -> Dict[str, str]:
    try:
        raw = base64.b64decode(req.image_b64)
        pil = Image.open(BytesIO(raw)).convert("RGB")
        img = np.array(pil)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid image payload") from exc

    results = OCR.readtext(img, detail=1)
    text = " ".join(t for _, t, _ in results if t.strip())
    return {"text": text}
