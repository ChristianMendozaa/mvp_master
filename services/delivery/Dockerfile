FROM python:3.13.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app app
COPY pyproject.toml uv.lock ./
COPY packages/python_common packages/python_common
COPY packages/python_observability packages/python_observability
COPY services/delivery services/delivery
RUN pip install --no-cache-dir uv==0.11.16 && uv sync --frozen --package mvp-delivery --no-dev
WORKDIR /app/services/delivery
USER app
EXPOSE 8000
CMD ["uvicorn", "mvp_delivery.entrypoints.api:app", "--host", "0.0.0.0", "--port", "8000"]
