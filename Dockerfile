FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py data_loader.py ./
EXPOSE 8050
CMD ["python", "app.py"]

