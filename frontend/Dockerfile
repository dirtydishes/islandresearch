FROM oven/bun:1

WORKDIR /app

COPY package.json tsconfig.json next.config.js ./
COPY next-env.d.ts ./next-env.d.ts
COPY src ./src

RUN bun install

EXPOSE 3000

CMD ["bun", "dev", "--host", "--port", "3000"]
