FROM python:3.11-slim

WORKDIR /app

# Install system deps for pdfplumber + lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Copy project
COPY . .

# Default query (override with docker run args)
ENV DASHSCOPE_API_KEY=""
ENV LLM_MODEL="qwen3-max"

ENTRYPOINT ["python", "-m", "agent.client"]
CMD ["给我生成一份关于 Pilbara 锂矿的今日简报"]
