# syntax=docker/dockerfile:1

# Production image for the Zate Trade web app.
# Debian-based (bookworm-slim) rather than Alpine: the dependency tree pulls
# native binaries (Sentry, SWC), and glibc avoids the musl edge cases those hit.

# ---------------------------------------------------------------------------
# Stage 1 — deps: install the full dependency tree, dev included
# ---------------------------------------------------------------------------
FROM node:20-bookworm-slim AS deps

WORKDIR /app

# puppeteer is a devDependency used only by local screenshot tooling. Its
# postinstall downloads ~150 MB of Chromium that no build step touches.
ENV PUPPETEER_SKIP_DOWNLOAD=true

COPY package.json package-lock.json ./

# The `prepare` script runs `cd .. && git config core.hooksPath frontend/.husky`.
# There is no git repository inside the image, so npm ci would abort on it.
# Dropping the script removes local hook wiring only — it has no build role.
RUN npm pkg delete scripts.prepare \
    && npm ci

# ---------------------------------------------------------------------------
# Stage 2 — builder: compile the Next.js standalone bundle
# ---------------------------------------------------------------------------
FROM node:20-bookworm-slim AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    PUPPETEER_SKIP_DOWNLOAD=true

# NEXT_PUBLIC_* values are inlined into the client bundle while it compiles, and
# next.config.js also reads NEXT_PUBLIC_API_URL to assemble the CSP connect-src.
# They must therefore arrive as build args — supplying them at runtime would
# leave the shipped bundle pointing at the localhost fallback.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# `prebuild` regenerates the legal pages before next build runs.
RUN npm pkg delete scripts.prepare \
    && npm run build

# ---------------------------------------------------------------------------
# Stage 3 — runtime: standalone server only
# ---------------------------------------------------------------------------
FROM node:20-bookworm-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# The standalone output carries its own trimmed node_modules; public/ and
# .next/static are not included in it and must be copied alongside.
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

# `node` (uid 1000) ships with the base image — no account creation needed.
USER node

EXPOSE 3000

# The standalone bundle's own server. Never `npm run dev`.
CMD ["node", "server.js"]
