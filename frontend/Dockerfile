FROM node:20-alpine

WORKDIR /app

# Install dependencies first
COPY package.json package-lock.json* ./
RUN npm install

# Copy source code
COPY . .

# Expose port and run dev server
EXPOSE 3000
CMD ["npm", "run", "dev"]
