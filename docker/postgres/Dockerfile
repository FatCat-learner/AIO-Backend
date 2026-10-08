FROM postgis/postgis:16-3.5

ARG PGVECTOR_VERSION=0.8.0

RUN printf '%s\n' \
        'deb http://snapshot.debian.org/archive/debian/20250721T000000Z bullseye main' \
        'deb http://snapshot.debian.org/archive/debian-security/20250721T000000Z bullseye-security main' \
        'deb http://snapshot.debian.org/archive/debian/20250721T000000Z bullseye-updates main' \
        > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        postgresql-server-dev-16 \
    && git clone --branch v${PGVECTOR_VERSION} --depth 1 \
        https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector \
    && make -C /tmp/pgvector install \
    && rm -rf /tmp/pgvector \
    && apt-get purge -y --auto-remove build-essential git postgresql-server-dev-16 \
    && rm -rf /var/lib/apt/lists/*
