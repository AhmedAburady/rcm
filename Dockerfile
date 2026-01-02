FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies
RUN uv sync --no-dev

# Set entrypoint to run rcm via uv
ENTRYPOINT ["uv", "run", "rcm"]
CMD ["--help"]
