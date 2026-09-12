# 1. Get a pre-built base image with Python installed
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy your requirement file and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# 4. Copy the rest of your application code
COPY . .

# 5. Tell the container how to start your web server (e.g., FastAPI)
CMD ["uvicorn", "api_app:app", "--host", "0.0.0.0", "--port", "8000"]