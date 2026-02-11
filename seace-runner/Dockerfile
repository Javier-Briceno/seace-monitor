FROM mcr.microsoft.com/playwright:v1.47.0-jammy

WORKDIR /app

# Install dependencies first (better Docker layer caching)
COPY package.json package-lock.json* ./
RUN npm install
RUN npx playwright install --with-deps chromium firefox

# Copy source code
COPY . .

EXPOSE 3000
CMD ["npm", "start"]
