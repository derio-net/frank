FROM python:3.12-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* /app/
COPY ai_alert_helper /app/ai_alert_helper
# Sync without dev deps; uv creates .venv
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

FROM python:3.12-slim
WORKDIR /app
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
USER 1000:1000
CMD ["uvicorn", "ai_alert_helper.api:app", "--host", "0.0.0.0", "--port", "8080"]
