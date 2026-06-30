FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY knowledge_agent /app/knowledge_agent

EXPOSE 8000

CMD ["uvicorn", "knowledge_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
