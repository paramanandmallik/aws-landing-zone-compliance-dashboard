FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir strands-agents boto3

# Copy agent code
COPY backend/ /app/backend/

ENV PYTHONPATH=/app
EXPOSE 8080

# AgentCore expects HTTP server on port 8080
CMD ["python", "-m", "backend.compliance_agent.server"]
