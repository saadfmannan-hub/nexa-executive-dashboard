FROM python:3.13-slim
WORKDIR /app
COPY . /app
ENV DAS_CLOUD_MODE=1 DAS_DEMO_MODE=1 DAS_DB_PATH=/tmp/dar_al_sultan_demo.db DAS_NO_BROWSER=1
EXPOSE 10000
CMD ["python", "server.py"]
