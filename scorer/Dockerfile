# The writing band model (specs/writing/step-2.3.md). PyTorch CPU build; weights are not in the
# image: they are downloaded once into the /models volume and checked against the pinned SHA-256.
FROM python:3.12-slim AS build
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim
RUN useradd --uid 10003 --create-home --shell /usr/sbin/nologin scorer \
 && mkdir -p /models && chown scorer /models
WORKDIR /srv
COPY --from=build /srv/.venv ./.venv
COPY nodetrail_scorer ./nodetrail_scorer
ENV PATH=/srv/.venv/bin:$PATH PYTHONUNBUFFERED=1 SCORER_HOST=0.0.0.0 SCORER_CACHE=/models \
    HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1
USER scorer
EXPOSE 8020
# The first start downloads about 500 MB; later starts load from the volume in seconds.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10m --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8020/health', timeout=3)"
CMD ["python", "-m", "nodetrail_scorer.server"]
