FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
COPY docs ./docs
COPY tests ./tests
COPY Makefile ./Makefile

RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -e .[dev]

CMD ["bash"]
