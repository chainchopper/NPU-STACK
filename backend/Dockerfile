# Build stage for llama.cpp tools
FROM python:3.11-slim AS llama-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone https://github.com/ggerganov/llama.cpp.git && \
    cd llama.cpp && \
    cmake -B build -DGGML_NATIVE=OFF -DGGML_LTO=ON && \
    cmake --build build --config Release -j$(nproc) --target llama-quantize llama-gguf-split llama-imatrix llama-cli llama-server

# Main stage
FROM python:3.11-slim

# System dependencies for OpenVINO, OpenCV, image processing, and HTTP requests
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled llama.cpp tools from builder to bin
COPY --from=llama-builder /build/llama.cpp/build/bin/llama-quantize /usr/local/bin/
COPY --from=llama-builder /build/llama.cpp/build/bin/llama-gguf-split /usr/local/bin/
COPY --from=llama-builder /build/llama.cpp/build/bin/llama-imatrix /usr/local/bin/
COPY --from=llama-builder /build/llama.cpp/build/bin/llama-cli /usr/local/bin/
COPY --from=llama-builder /build/llama.cpp/build/bin/llama-server /usr/local/bin/

# Fetch convert script
RUN curl -sSL -o /usr/local/bin/convert_hf_to_gguf.py https://raw.githubusercontent.com/ggerganov/llama.cpp/master/convert_hf_to_gguf.py && \
    curl -sSL -o /usr/local/bin/convert_llama_ggml_to_gguf.py https://raw.githubusercontent.com/ggerganov/llama.cpp/master/convert_llama_ggml_to_gguf.py

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
# Install llama-cpp-python separately (optional; graceful failure if build unavailable)
RUN pip install --no-cache-dir llama-cpp-python --prefer-binary || \
    echo "WARNING: llama-cpp-python install failed. GGUF inference via Python will be unavailable."
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data/models data/datasets

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
