# ── Stage 1: train ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS trainer

WORKDIR /workspace

RUN pip install --no-cache-dir tensorflow==2.16.1 numpy==1.26.4

COPY model/train.py model/train.py

# Train the model; weights land at model/cifar10_model.h5
# Set EPOCHS env var to shorten training (default 20)
ARG EPOCHS=20
ENV EPOCHS=${EPOCHS}
ENV MODEL_PATH=model/cifar10_model.h5

RUN python model/train.py


# ── Stage 2: serve ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS server

WORKDIR /app

# System deps for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy trained weights from Stage 1
COPY --from=trainer /workspace/model/cifar10_model.h5   model/cifar10_model.h5
COPY --from=trainer /workspace/model/cifar10_model_norm.npz model/cifar10_model_norm.npz

# Copy application code
COPY app/ .

ENV MODEL_PATH=model/cifar10_model.h5
ENV NORM_PATH=model/cifar10_model_norm.npz
ENV TOP_K=3

# Knative injects PORT at runtime (default 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
