"""
CIFAR-10 inference service — FastAPI
Deployed as a Knative serverless function in the 5G data network.

Flow: UE → gNB → UPF → Knative Ingress → this service
"""
import io
import os
import time
import logging
from contextlib import asynccontextmanager

import numpy as np
import tensorflow as tf
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image

from cifar10_classes import CIFAR10_CLASSES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("MODEL_PATH", "model/cifar10_model.h5")
NORM_PATH  = os.environ.get("NORM_PATH",  "model/cifar10_model_norm.npz")
TOP_K      = int(os.environ.get("TOP_K", "3"))

# Module-level state loaded once at startup
_model: tf.keras.Model = None
_mean:  np.ndarray     = None
_std:   np.ndarray     = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _mean, _std

    log.info("Loading model from %s", MODEL_PATH)
    t0 = time.perf_counter()
    _model = tf.keras.models.load_model(MODEL_PATH)
    # warm-up pass so first real request isn't slow
    _model.predict(np.zeros((1, 32, 32, 3), dtype="float32"), verbose=0)

    norm = np.load(NORM_PATH)
    _mean, _std = norm["mean"], norm["std"]
    log.info("Model ready in %.2fs", time.perf_counter() - t0)

    yield

    log.info("Shutting down")


app = FastAPI(
    title="CIFAR-10 Inference Service",
    description="Serverless image classification for 5G MEC. POST an image, get the predicted class.",
    version="1.0.0",
    lifespan=lifespan,
)


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Decode, resize to 32×32, normalize with training stats."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot decode image: {exc}")

    img = img.resize((32, 32), Image.LANCZOS)
    arr = np.array(img, dtype="float32") / 255.0
    arr = (arr - _mean) / _std
    return np.expand_dims(arr, axis=0)  # (1, 32, 32, 3)


@app.get("/", tags=["info"])
def root():
    return {
        "service": "cifar10-faas",
        "version": "1.0.0",
        "classes": CIFAR10_CLASSES,
        "usage": "POST /predict  with multipart/form-data field 'file'",
    }


@app.get("/health", tags=["probe"])
def health():
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ok"}


@app.post("/predict", tags=["inference"])
async def predict(file: UploadFile = File(..., description="Image file (JPEG/PNG/BMP)")):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    t0 = time.perf_counter()
    tensor = preprocess(raw)
    probs  = _model.predict(tensor, verbose=0)[0]           # shape (10,)
    latency_ms = (time.perf_counter() - t0) * 1000

    top_indices = np.argsort(probs)[::-1][:TOP_K]
    top_results = [
        {"rank": i + 1, "class": CIFAR10_CLASSES[idx], "confidence": float(probs[idx])}
        for i, idx in enumerate(top_indices)
    ]

    log.info(
        "predict | file=%s top1=%s conf=%.4f latency=%.1fms",
        file.filename, top_results[0]["class"], top_results[0]["confidence"], latency_ms,
    )

    return JSONResponse({
        "prediction":  top_results[0]["class"],
        "confidence":  top_results[0]["confidence"],
        "top_k":       top_results,
        "latency_ms":  round(latency_ms, 2),
        "filename":    file.filename,
    })
