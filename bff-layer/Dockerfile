# Dockerfile untuk TypeScript Backend For Frontend (BFF) Layer
FROM node:18-alpine

WORKDIR /app

# Salin manifest dependensi
COPY package.json ./
COPY tsconfig.json ./

# Install dependensi
RUN npm install

# Salin seluruh berkas kode BFF
COPY . .

# Compile TypeScript ke JavaScript
RUN npm run build

# Port yang dibuka untuk Web BFF
EXPOSE 3000

# Healthcheck (liveness): /health 200
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["npm", "run", "start"]
