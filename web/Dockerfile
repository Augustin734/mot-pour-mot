# Image du front Next.js en sortie « standalone » (seuls les fichiers utiles au serveur).
FROM node:24-alpine AS construction
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=construction /app/.next/standalone ./
COPY --from=construction /app/.next/static ./.next/static
COPY --from=construction /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
