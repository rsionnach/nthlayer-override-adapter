FROM python:3.11-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1

RUN pip install --no-cache-dir uv==0.5.0

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --no-dev --frozen
RUN uv build --wheel

FROM python:3.11-slim

RUN useradd --create-home --shell /bin/bash adapter
WORKDIR /home/adapter

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

USER adapter
EXPOSE 8090

ENTRYPOINT ["nthlayer-override-adapter", "serve"]
CMD ["--host", "0.0.0.0", "--port", "8090"]
