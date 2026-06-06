FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-trained model files (generated once via model/train.py)
COPY model/cifar10_model.h5      model/cifar10_model.h5
COPY model/cifar10_model_norm.npz model/cifar10_model_norm.npz

COPY app/ .

ENV MODEL_PATH=model/cifar10_model.h5
ENV NORM_PATH=model/cifar10_model_norm.npz
ENV TOP_K=3
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
