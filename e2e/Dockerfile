FROM mcr.microsoft.com/playwright:v1.44.0-jammy

WORKDIR /app
COPY package*.json ./
RUN npm ci
RUN npx playwright install --with-deps chromium

COPY . .

CMD ["npx", "playwright", "test", "--reporter=list"]
