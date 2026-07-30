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

CMD ["npm", "run", "start"]
