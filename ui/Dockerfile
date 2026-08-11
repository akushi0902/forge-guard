# ForgeGuard UI — Multi-stage Docker build
#
# Stage 1 (builder): Node 20 LTS installs dependencies and produces a
#                    production-optimised Vite bundle in dist/.
# Stage 2 (runtime): Nginx Alpine serves the static bundle with security
#                    headers and SPA fallback routing.
#
# Build:
#   docker build -t forgeguard-ui:latest .
#
# Run:
#   docker run -p 80:80 forgeguard-ui:latest

# ============================================================ #
# Stage 1: builder
# ============================================================ #
FROM node:20-alpine AS builder

WORKDIR /app

# Copy manifest files first — Docker layer caching skips npm ci when only
# source files changed.
COPY package.json package-lock.json* ./

# Install all dependencies (including dev deps needed for build).
RUN npm ci --ignore-scripts

# Copy source and build.
COPY . .

# Type-check and build the production bundle.
RUN npm run build

# ============================================================ #
# Stage 2: runtime
# ============================================================ #
FROM nginx:1.27-alpine AS runtime

LABEL org.opencontainers.image.title="ForgeGuard UI"
LABEL org.opencontainers.image.description="ForgeGuard React SPA — served by Nginx"

# Remove the default Nginx configuration.
RUN rm /etc/nginx/conf.d/default.conf

# Copy our custom Nginx configuration.
COPY nginx.conf /etc/nginx/conf.d/forgeguard.conf

# Copy the Vite production bundle from the builder stage.
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx listens on port 80 inside the container.
EXPOSE 80

# Run Nginx in the foreground (required for Docker PID 1).
CMD ["nginx", "-g", "daemon off;"]
