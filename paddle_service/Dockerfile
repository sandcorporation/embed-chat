FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    FLAGS_use_mkldnn=0 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

ARG PADDLE_GPU_INDEX_URL=https://www.paddlepaddle.org.cn/packages/stable/cu126/
ARG PADDLEPADDLE_GPU_VERSION=3.1.1
ARG PADDLEOCR_VERSION=3.5.0

RUN pip install --no-cache-dir \
    --index-url ${PADDLE_GPU_INDEX_URL} \
    --extra-index-url https://pypi.org/simple \
    paddlepaddle-gpu==${PADDLEPADDLE_GPU_VERSION} \
    paddleocr==${PADDLEOCR_VERSION}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
