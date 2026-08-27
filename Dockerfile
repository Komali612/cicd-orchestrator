# FROZEN — identical in every agent repo.
# Multi-stage: install into a builder, copy into a slim runtime.
FROM python:3.11-slim AS build
WORKDIR /app
# git is required to pip-install agent-core from its git repo (see pyproject.toml)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
ENTRYPOINT ["agent"]
