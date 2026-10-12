# Multi-architecture, digest-pinned build tools; no host Python/uv is needed.
FROM ghcr.io/astral-sh/uv:0.11.15@sha256:e590846f4776907b254ac0f44b5b380347af5d90d668138ca7938d1b0c2f98d3 AS uv
FROM docker:29.8.2-cli@sha256:35cfcf893c20f2931f4909151b5407aaaeab711277de7ce8b8f521f095d54c32 AS dockercli
FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python

FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dependencies /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 POD_DATA_DIR=/data
WORKDIR /app
COPY arena/ arena/
COPY web/ web/
COPY examples/ examples/
COPY scripts/container_entrypoint.py scripts/deployment_probe.py scripts/
# The trusted app requires daemon access. Student containers are separately
# non-root and receive neither this socket nor any other host mount.
EXPOSE 8765
ENTRYPOINT ["python", "scripts/container_entrypoint.py"]
