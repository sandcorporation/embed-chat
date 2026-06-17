FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM alpine:3.19
COPY --from=build /app/dist /dist
CMD ["sh", "-c", "cp -r /dist/. /output/"]
