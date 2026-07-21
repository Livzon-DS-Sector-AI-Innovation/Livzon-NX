FROM node:20-alpine AS builder

WORKDIR /app

RUN npm install -g pnpm@10.33.0

RUN npm config set registry https://registry.npmmirror.com

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL=
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV API_BASE_URL=http://backend:8000
ENV NODE_ENV=production

RUN pnpm build

# Runtime stage — uses Next.js standalone output
FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
