# API and worker image (same image, different command). Build from the repository root:
#   docker build -f apps/api/Dockerfile -t nodetrail-api .
# The repository layout is kept under /srv so paths derived from the source tree
# (supabase/migrations, data/courses, data/sources) resolve as in a checkout.
FROM python:3.12-slim AS build
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv/apps/api
COPY --from=build /srv/apps/api/.venv ./.venv
COPY apps/api/app ./app
COPY supabase/migrations /srv/supabase/migrations
COPY data /srv/data
ENV PATH=/srv/apps/api/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.main:create_content_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
