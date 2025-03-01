FROM python:3.10-slim

WORKDIR /app

# Install git and curl to clone the repository and install uv
RUN apt-get update && \
    apt-get install -y git curl ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Clone only the open_deep_research folder from smolagents repository
COPY open_deep_research /app/open_deep_research

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Set the PATH to include uv
ENV PATH="/root/.local/bin:$PATH"

# Set up the Python environment
WORKDIR /app/open_deep_research
RUN uv init && \
    uv venv && \
    uv pip install -r requirements.txt --index-strategy unsafe-best-match

# Set the entrypoint
ENTRYPOINT ["uv", "run", "run.py"]
CMD ["What is the meaning of life?"]