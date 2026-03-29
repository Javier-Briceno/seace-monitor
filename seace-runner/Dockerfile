FROM mcr.microsoft.com/playwright:v1.47.0-jammy

WORKDIR /app

# unar: extraction of RAR archives (RAR3 and RAR5). Available in Ubuntu Jammy without extra repositories.
# Preconfigure tzdata to avoid an interactive prompt when installing unar.
# TZ=America/Lima matches the production server timezone (Peru, UTC-5).
RUN ln -fs /usr/share/zoneinfo/America/Lima /etc/localtime && \
    echo "America/Lima" > /etc/timezone && \
    DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata unar && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies first (better Docker layer caching)
COPY package.json package-lock.json* ./
RUN npm install
RUN npx playwright install --with-deps chromium firefox

# Copy source code
COPY . .

EXPOSE 3000
CMD ["npm", "start"]
