FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY app ./app
COPY eval ./eval
COPY data/manifests ./data/manifests

RUN pip install --no-cache-dir uv==0.13.1 \
    && uv sync --locked --no-dev --no-editable --no-cache --python /usr/local/bin/python

EXPOSE 9101

CMD ["python", "-m", "uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "9101"]
