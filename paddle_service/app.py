# pyright: reportMissingImports=false

from __future__ import annotations

import base64
from io import BytesIO
import os
from typing import Any, Dict, List

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from paddleocr import PaddleOCR
from PIL import Image

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")

app = FastAPI(title="Paddle OCR Service", version="1.0.0")


class OcrRequest(BaseModel):
    image_b64: str


def _collect_text_tokens(node: Any, out: List[str]) -> None:
    if isinstance(node, str):
        s = node.strip()
        if s:
            out.append(s)
        return

    if isinstance(node, dict):
        rec_texts = node.get("rec_texts")
        if isinstance(rec_texts, list):
            for value in rec_texts:
                _collect_text_tokens(value, out)

        rec_text = node.get("rec_text")
        if isinstance(rec_text, str):
            _collect_text_tokens(rec_text, out)

        return

    if isinstance(node, (list, tuple)):
        if len(node) == 2 and isinstance(node[0], str):
            _collect_text_tokens(node[0], out)
            return

        for value in node:
            _collect_text_tokens(value, out)


def _extract_text_from_ocr_result(result: Any) -> str:
    if not result:
        return ""

    texts: List[str] = []
    _collect_text_tokens(result, texts)

    return " ".join(texts).strip()


def _init_ocr() -> PaddleOCR:
    # Try new-style API (PP-OCRv5) with GPU first
    new_style_kwargs = dict(
        lang="ch",
        ocr_version="PP-OCRv5",
        enable_mkldnn=False,
        enable_hpi=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    for device in ("gpu", "cpu"):
        try:
            return PaddleOCR(**new_style_kwargs, device=device)
        except Exception:
            pass

    # Fall back to older paddleocr API (CPU)
    return PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=False, show_log=False)


OCR = _init_ocr()


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

    result = OCR.ocr(img)
    text = _extract_text_from_ocr_result(result)
    return {"text": text}
