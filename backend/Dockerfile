# syntax=docker/dockerfile:1

# Production image for the Zate Trade API.
# Postgres (Supabase) and Redis (Upstash) are external services — nothing is
# provisioned here beyond the application itself.

# ---------------------------------------------------------------------------
# Stage 1 — builder: resolve dependencies into an isolated virtualenv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Compiler toolchain for any dependency without a manylinux wheel. It lives and
# dies in this stage — the runtime image never sees it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# requirements.lock is the fully pinned set (119 packages, transitive deps
# included). requirements.txt lists only direct dependencies, so it would let
# transitive versions drift between builds.
COPY requirements.lock ./
RUN pip install --upgrade pip \
    && pip install -r requirements.lock

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libgomp1 is loaded at runtime by the numpy/pandas manylinux wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

# Unprivileged from here on: a container escape lands on a nologin account that
# owns nothing outside /app.
USER app

EXPOSE 8000

# Mirrors railway.json and Procfile:
#   --workers 1          APScheduler runs in-process; a second worker would fire
#                        every signal and resolution twice.
#   --proxy-headers      rate limiting and the bot challenge key on the real
#   --forwarded-allow-ips  client IP rather than Nginx's address.
# No --reload: that is a development-only flag.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
