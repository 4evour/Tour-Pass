FROM ubuntu:24.04 AS build

ENV DEBIAN_FRONTEND=noninteractive

RUN for i in 1 2 3; do apt-get update && break || sleep 5; done \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        libssl-dev \
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
    && cmake --build build --config Release --target tourpass -j2 \
    && ls -la build/tourpass

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    HOST=0.0.0.0 \
    PORT=8080 \
    LLM_DISABLED=1 \
    TOURPASS_DB_PATH=/app/storage/tourpass.sqlite

RUN for i in 1 2 3; do apt-get update && break || sleep 5; done \
    && apt-get install -y --no-install-recommends ca-certificates libssl3 \
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
