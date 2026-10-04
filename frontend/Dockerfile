FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
ARG SONAR_MODE=demo
ARG SONAR_API_BASE=
ENV NEXT_PUBLIC_SONAR_MODE=${SONAR_MODE}
ENV NEXT_PUBLIC_SONAR_API_BASE=${SONAR_API_BASE}
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start", "--", "--host", "0.0.0.0", "--port", "3000"]
