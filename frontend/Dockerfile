# Multi-stage build: Node build → Nginx serve
FROM node:20-slim AS builder

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
