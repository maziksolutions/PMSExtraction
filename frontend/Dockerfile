FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WS_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build

FROM nginx:alpine
RUN apk add --no-cache ca-certificates
COPY --from=builder /app/dist /usr/share/nginx/html
RUN printf 'client_max_body_size 100m;\n\
server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location /api/ {\n\
    proxy_pass https://web-production-c592.up.railway.app/api/;\n\
    proxy_set_header Host web-production-c592.up.railway.app;\n\
    proxy_set_header X-Real-IP $remote_addr;\n\
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    proxy_ssl_server_name on;\n\
  }\n\
  location /health {\n\
    proxy_pass https://web-production-c592.up.railway.app/health;\n\
    proxy_set_header Host web-production-c592.up.railway.app;\n\
    proxy_ssl_server_name on;\n\
  }\n\
  location / {\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
