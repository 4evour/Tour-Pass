FROM ubuntu:24.04 AS build

ENV DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ubuntu/

RUN sed -i "s|http://archive.ubuntu.com/ubuntu/|${UBUNTU_APT_MIRROR}|g; s|http://security.ubuntu.com/ubuntu/|${UBUNTU_APT_MIRROR}|g" /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .

RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --config Release --target tourpass

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    HOST=0.0.0.0 \
    PORT=8080 \
    LLM_DISABLED=1 \
    TOURPASS_DB_PATH=/app/storage/tourpass.sqlite
ARG UBUNTU_APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ubuntu/

RUN sed -i "s|http://archive.ubuntu.com/ubuntu/|${UBUNTU_APT_MIRROR}|g; s|http://security.ubuntu.com/ubuntu/|${UBUNTU_APT_MIRROR}|g" /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin tourpass

WORKDIR /app
COPY --from=build /src/build/tourpass /app/tourpass
COPY data /app/data
COPY web /app/web

RUN mkdir -p /app/config /app/storage \
    && chown -R tourpass:tourpass /app

COPY --chown=tourpass:tourpass config/llm.example.json /app/config/llm.example.json

USER tourpass
EXPOSE 8080

CMD ["/app/tourpass"]
