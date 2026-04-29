# fidu -- runtime image
#
# Build:        docker build -t fidu:latest .
# Run a config: docker run --rm -v "$(pwd)/configs:/app/configs:ro" \
#                          -v "$(pwd)/rules:/app/rules:ro" \
#                          -v "$(pwd)/data:/app/data:ro" \
#                          -v "$(pwd)/outputs:/app/outputs" \
#                          fidu:latest \
#                          --config configs/dq_config.yaml
#
# Tag-and-push for an internal registry:
#   docker build -t registry.internal/fidu:1.0.0 .
#   docker push registry.internal/fidu:1.0.0
#
# Notes:
# * Stays slim: only ``[lite]`` deps (pandas + duckdb + pyarrow + pyyaml).
#   For Soda/GX support, install with ``--build-arg EXTRAS=tools`` or build
#   a downstream image FROM fidu + ``pip install soda-core``.
# * Runs as a non-root ``dq`` user.
# * No build tools in the final image -- multi-stage keeps the runtime small.

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG EXTRAS=""

WORKDIR /build

# Build deps for pyarrow / pandas / pyyaml wheels are pre-built on PyPI for
# linux/amd64 + linux/arm64 -- no apt-get needed when targeting those.
COPY pyproject.toml README.md ./
COPY fidu ./fidu

RUN pip install --prefix=/install ".${EXTRAS:+[$EXTRAS]}"


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Non-root user -- runs as uid/gid 1001.
RUN groupadd --system --gid 1001 dq \
    && useradd --system --gid dq --uid 1001 --create-home --home-dir /home/dq dq

WORKDIR /app

COPY --from=builder /install /usr/local
COPY fidu ./fidu
COPY schemas ./schemas

RUN mkdir -p /app/outputs && chown -R dq:dq /app

USER dq

ENTRYPOINT ["python", "-m", "fidu.main"]
CMD ["--config", "configs/dq_config.yaml"]
