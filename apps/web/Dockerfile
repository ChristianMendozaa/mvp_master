FROM node:24.7.0-alpine AS dependencies
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @mvp-master/web...

FROM dependencies AS builder
COPY apps/web apps/web
RUN pnpm --filter @mvp-master/web build

FROM node:24.7.0-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup --system --gid 10001 app && adduser --system --uid 10001 --ingroup app app
COPY --from=builder --chown=app:app /app/apps/web/.next/standalone ./
COPY --from=builder --chown=app:app /app/apps/web/.next/static ./apps/web/.next/static
USER app
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
