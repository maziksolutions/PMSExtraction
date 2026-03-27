# --- Stage 1: Build ---
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package manifests first for layer caching
COPY package*.json ./

# Install all deps (including devDeps needed to build)
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# --- Stage 2: Serve ---
FROM nginx:1.25-alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config (API proxy + SPA routing)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
