# Rebuild trigger v2 - with Python Agent
FROM ubuntu:24.04 AS build

ENV DEBIAN_FRONTEND=noninteractive

RUN echo "=== Step 1: apt-get update ===" \
    && apt-get update 2>&1 \
    && echo "=== Step 2: apt-get install ===" \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        libssl-dev \
        libpq-dev 2>&1 \
    && echo "=== Step 3: cleanup ===" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY CMakeLists.txt Makefile ./
COPY include include
COPY src src
COPY third_party third_party
COPY data data
COPY web web
COPY config config

RUN echo "=== Step 4: cmake configure ===" \
    && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release 2>&1 \
    && echo "=== Step 5: cmake build ===" \
    && cmake --build build --config Release --target tourpass -j2 2>&1 \
    && echo "=== Step 6: verify binary ===" \
    && ls -la build/tourpass

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    HOST=0.0.0.0 \
    PORT=8080 \
    AGENT_PORT=8090 \
    TOURPASS_MAX_BODY_BYTES=262144 \
    TOURPASS_DB_PATH=/app/storage/tourpass.sqlite \
    PYTHONUNBUFFERED=1

RUN apt-get update 2>&1 \
    && apt-get install -y --no-install-recommends \
        ca-certificates libssl3 libpq5 curl \
        python3 python3-pip python3-venv 2>&1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin tourpass

WORKDIR /app

# Copy C++ backend
COPY --from=build /src/build/tourpass /app/tourpass
COPY --from=build /src/data /app/data
COPY --from=build /src/web /app/web

# Copy Agent service
COPY agent/ /app/agent/
COPY scripts/ /app/scripts/

# Install Python dependencies into venv
RUN python3 -m venv /app/venv \
    && /app/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /app/venv/bin/pip install --no-cache-dir \
        fastapi>=0.115.0 \
        "uvicorn[standard]>=0.30.0" \
        pydantic>=2.0 \
        httpx>=0.27.0 \
        "langchain-core>=0.3.0" \
        "langchain-openai>=0.2.0" \
        python-dotenv>=1.0.0

# ChromaDB + embedding (optional, large download)
# Comment out the next line to skip RAG support for faster builds
RUN /app/venv/bin/pip install --no-cache-dir chromadb>=0.5.0 \
    || echo "WARN: ChromaDB install failed, RAG will be disabled"

# Create directories
RUN mkdir -p /app/config /app/storage /app/scripts \
    && chown -R tourpass:tourpass /app

COPY --chown=tourpass:tourpass config/llm.example.json /app/config/llm.example.json
COPY --chown=tourpass:tourpass entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER tourpass
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["/app/entrypoint.sh"]
