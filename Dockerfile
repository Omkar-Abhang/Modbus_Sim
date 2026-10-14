# Stage 1: build the React UI
FROM node:20-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

# Stage 2: simulator (API + UI + Modbus TCP server in one process)
FROM python:3.10-slim
ENV TZ=Asia/Kolkata PYTHONUNBUFFERED=1 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./
COPY src/ ./src/
COPY --from=ui /ui/dist ./ui/dist
EXPOSE 15001 5020
CMD ["python", "main.py"]
