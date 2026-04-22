# syntax=docker/dockerfile:1.7
#
# main_agent — FastAPI + Pydantic AI service. Connects to MCP servers
# listed in mcp_servers.yaml and exposes /chat for clients.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy project metadata first so the dependency layer caches independently
# of source changes.
COPY pyproject.toml ./
COPY src ./src

RUN pip install --upgrade pip \
 && pip install .

# The registry YAML ships with the image; env vars fill in URLs/tokens.
COPY mcp_servers.yaml ./

ENV BIND_HOST=0.0.0.0 \
    BIND_PORT=9000 \
    MCP_CONFIG_PATH=/app/mcp_servers.yaml \
    HISTORY_DB_PATH=/app/data/conversations.db

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,os,sys;\
port=os.environ.get('BIND_PORT','9000');\
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3).status==200 else 1)"

ENTRYPOINT ["main-agent"]
