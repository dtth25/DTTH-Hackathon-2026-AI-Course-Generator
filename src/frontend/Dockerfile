FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
# BACKEND_INTERNAL_URL must be present at BUILD time, not just runtime: next.config.ts's
# rewrites() is evaluated during `next build` and baked into routes-manifest.json (with
# output:"standalone"). Setting it only via runtime `environment:` in docker-compose has
# no effect — the proxy destination is already frozen. Unset here would bake the
# localhost:8000 fallback and every /api/* proxy hop would ECONNREFUSED in prod. Default
# to the compose service name; override via build arg if the backend service is renamed.
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# Next standalone output excludes public assets, so copy them explicitly into the
# runtime image. Without this, landing screenshots return 404 in Docker even though
# they work under `next dev`.
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
