FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" packgraph

COPY requirements.txt pyproject.toml setup.py README.md /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app
COPY agents /app/agents
COPY scripts /app/scripts
COPY web /app/web
COPY data /app/data
COPY queries /app/queries
COPY docs /app/docs
COPY .env.example /app/.env.example

RUN chown -R packgraph:packgraph /app
USER packgraph

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
