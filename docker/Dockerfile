FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY taskforge ./taskforge
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[postgres]"

FROM python:3.12-slim
RUN groupadd --gid 10001 taskforge && useradd --uid 10001 --gid taskforge --create-home taskforge
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /data
RUN chown taskforge:taskforge /data
USER taskforge
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=3)"
CMD ["taskforge", "server", "start", "--host", "0.0.0.0", "--port", "8080"]
