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
ENV BACKEND_UPSTREAM=https://web-production-c592.up.railway.app
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
