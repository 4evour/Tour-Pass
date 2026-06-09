# TourPass with Agent - optimized for Render free tier
FROM ubuntu:24.04 AS build

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake libssl-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY CMakeLists.txt Makefile ./
COPY include include
COPY src src
COPY third_party third_party
COPY data data
COPY web web
COPY config config

RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --config Release --target tourpass -j2

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    HOST=0.0.0.0 PORT=8080 AGENT_PORT=8090 \
    TOURPASS_MAX_BODY_BYTES=262144 \
    TOURPASS_DB_PATH=/app/storage/tourpass.sqlite \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libssl3 libpq5 curl python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin tourpass

WORKDIR /app

COPY --from=build /src/build/tourpass /app/tourpass
COPY --from=build /src/data /app/data
COPY --from=build /src/web /app/web
COPY agent/ /app/agent/
COPY scripts/ /app/scripts/

# Install only core Agent deps (skip heavy optional packages)
RUN pip3 install --no-cache-dir --break-system-packages \
    fastapi uvicorn pydantic httpx \
    langchain-core langchain-openai python-dotenv

# Verify Agent imports work
RUN python3 -c "import agent.main; print('Agent module OK')" || echo "WARN: Agent import failed"

RUN mkdir -p /app/config /app/storage \
    && chown -R tourpass:tourpass /app

COPY --chown=tourpass:tourpass config/llm.example.json /app/config/llm.example.json
COPY --chown=tourpass:tourpass entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER tourpass
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["/app/entrypoint.sh"]
