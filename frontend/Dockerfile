FROM node:20-alpine

WORKDIR /app

# Install dependencies first
COPY package.json package-lock.json* ./
RUN npm install

# Copy source code
COPY . .

# Build app for production runtime
RUN npm run build

# Expose port and run production server
EXPOSE 3000
CMD ["sh", "-lc", "npm run start -- -H 0.0.0.0 -p ${PORT:-3000}"]
