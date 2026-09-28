FROM python:3.12-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8501

CMD ["streamlit", "run", "versa/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
