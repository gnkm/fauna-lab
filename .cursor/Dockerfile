# Cursor Cloud Agent の VM 用。アプリの実行イメージ（リポジトリ直下の
# Containerfile / Dockerfile）とは役割が違う。プロジェクトは COPY しない
# （Cursor がワークスペースをチェックアウトする）。
#
# ローカル / 提出は Podman。Cloud では同一 OCI を Docker Compose で動かすため
# Docker CE を入れる。公式の Docker-in-Docker 断片（fuse-overlayfs /
# iptables-legacy）に、Python 3.12・Node 22・uv を足す。

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    PATH="/usr/local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        git \
        jq \
        sudo \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        iptables \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22（pnpm は corepack。版は packageManager に合わせる）
RUN curl --retry 3 --retry-delay 5 -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && corepack enable \
    && corepack prepare pnpm@10.33.3 --activate \
    && rm -rf /var/lib/apt/lists/*

# uv は Containerfile と同じ版。Ubuntu 24.04 の pip は PEP 668 で user インストールが落ちる。
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv

########################################################
# DOCKER INSTALLATION
########################################################

RUN install -m 0755 -d /etc/apt/keyrings && \
    curl --retry 3 --retry-delay 5 -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y \
    docker-ce=5:28.5.2-1~ubuntu.24.04~noble \
    docker-ce-cli=5:28.5.2-1~ubuntu.24.04~noble \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends fuse-overlayfs && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /etc/docker && \
    printf '%s\n' '{' \
    '  "storage-driver": "fuse-overlayfs"' \
    '}' > /etc/docker/daemon.json
RUN update-alternatives --set iptables /usr/sbin/iptables-legacy && \
    update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy

########################################################
# CONFIG UBUNTU USER
########################################################

RUN mkdir -p /etc/ssh/sshd_config.d && \
    echo 'PasswordAuthentication no\nChallengeResponseAuthentication no\nUsePAM no' > /etc/ssh/sshd_config.d/disable_password_auth.conf

RUN id -u ubuntu >/dev/null 2>&1 || useradd -m -s /bin/bash ubuntu
RUN groupadd -f docker && usermod -aG docker ubuntu
RUN usermod -aG sudo ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu
RUN echo "ubuntu:ubuntu" | chpasswd
