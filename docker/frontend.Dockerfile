FROM node:20-alpine AS build
WORKDIR /app
# låsfilen med: utan den installerar två byggen olika versioner, och det ena fungerar
COPY frontend/package.json frontend/package-lock.json* /app/
RUN npm install --no-audit --no-fund
COPY frontend /app
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
