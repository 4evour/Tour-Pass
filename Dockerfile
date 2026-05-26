FROM ubuntu:24.04 AS build

ENV DEBIAN_FRONTEND=noninteractive

RUN echo "=== Step 1: apt-get update ===" \
    && apt-get update 2>&1 \
    && echo "=== Step 2: apt-get install ===" \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        libssl-dev 2>&1 \
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

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    HOST=0.0.0.0 \
    PORT=8080 \
    LLM_DISABLED=1 \
    TOURPASS_DB_PATH=/app/storage/tourpass.sqlite

RUN apt-get update 2>&1 \
    && apt-get install -y --no-install-recommends ca-certificates libssl3 2>&1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin tourpass

WORKDIR /app
COPY --from=build /src/build/tourpass /app/tourpass
COPY --from=build /src/data /app/data
COPY --from=build /src/web /app/web

RUN mkdir -p /app/config /app/storage \
    && chown -R tourpass:tourpass /app

COPY --chown=tourpass:tourpass config/llm.example.json /app/config/llm.example.json

USER tourpass
EXPOSE 8080

CMD ["/app/tourpass"]
