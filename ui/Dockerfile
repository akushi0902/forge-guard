# ForgeGuard UI — Multi-stage Docker build
#
# Stage 1 (builder): Node 20 Alpine installs dependencies and produces a
#                    production-optimised Vite bundle in dist/.
# Stage 2 (runtime): Nginx 1.27 Alpine serves the static bundle with TLS
#                    termination, security headers, and API reverse-proxy.
#
# Self-signed TLS certificates are generated at build time for the
# demo/development environment. Production deployments should replace
# the RUN openssl step with COPY of CA-signed certificates.
#
# Build:
#   docker build -t forgeguard-ui:latest .
#
# Run standalone (without docker-compose):
#   docker run -p 80:80 -p 443:443 forgeguard-ui:latest

# ============================================================ #
# Stage 1: builder
# ============================================================ #
FROM node:20-alpine AS builder

WORKDIR /app

# Copy manifest files first — Docker layer caching skips npm ci when only
# source files change.
COPY package.json package-lock.json* ./

# Install all dependencies (including dev deps needed for the build).
RUN npm ci --ignore-scripts

# Copy source files and build configuration.
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json ./
COPY src/ src/
COPY public/ public/

# Type-check and produce the production bundle in dist/.
RUN npm run build

# ============================================================ #
# Stage 2: runtime
# ============================================================ #
FROM nginx:1.27-alpine AS runtime

LABEL org.opencontainers.image.title="ForgeGuard UI"
LABEL org.opencontainers.image.description="ForgeGuard React SPA — Nginx with TLS, security headers, and API proxy"

# Remove default Nginx config to avoid conflicts.
RUN rm -f /etc/nginx/conf.d/default.conf

# ---- Nginx configuration ------------------------------------------------ #
COPY nginx/nginx.conf       /etc/nginx/nginx.conf
COPY nginx/conf.d/          /etc/nginx/conf.d/
COPY nginx/snippets/        /etc/nginx/snippets/

# ---- Self-signed TLS certificate ---------------------------------------- #
# Generate a self-signed certificate for the demo environment.
# Production: replace this RUN block with COPY of CA-signed certificates.
RUN apk add --no-cache openssl && \
    mkdir -p /etc/nginx/ssl && \
    openssl req \
        -x509 \
        -nodes \
        -days 365 \
        -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/key.pem \
        -out    /etc/nginx/ssl/cert.pem \
        -subj   "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" && \
    chmod 600 /etc/nginx/ssl/key.pem && \
    chmod 644 /etc/nginx/ssl/cert.pem

# ---- Nginx config syntax validation --------------------------------------#
# NOTE: nginx -t is intentionally NOT run here at build time. This config
# references the Docker Compose service name `forgeguard-backend` in an
# `upstream` block, which nginx resolves at config-load time — but that
# hostname only exists on the `forgeguard-net` Compose network, which the
# isolated build container is never attached to. Running `nginx -t` here
# always fails with "host not found in upstream", even for a valid config.
# Real validation happens in the CMD below, at container start, once the
# container has actually joined the Compose network and the hostname
# resolves — that's the earliest point this config can be truthfully tested.

# ---- React SPA bundle --------------------------------------------------- #
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx listens on port 80 (HTTP → redirect) and 443 (HTTPS).
EXPOSE 80 443

# Validate config, then run Nginx in the foreground (required for Docker PID 1).
# `nginx -t` here runs after the container has joined the Compose network, so
# the `forgeguard-backend` upstream hostname resolves and the check is real —
# a genuinely broken config still fails fast, with a clear error in
# `docker compose logs`, instead of the container silently crash-looping.
CMD ["sh", "-c", "nginx -t && exec nginx -g 'daemon off;'"]
