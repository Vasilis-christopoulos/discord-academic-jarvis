FROM public.ecr.aws/lambda/python:3.10

# Set environment variables to force all temp and cache operations to use /tmp
ENV TMPDIR=/tmp
ENV TMP=/tmp
ENV TEMP=/tmp
ENV HOME=/tmp
ENV TRANSFORMERS_CACHE=/tmp/.cache/huggingface
ENV HF_HOME=/tmp/.cache/huggingface
ENV XDG_CACHE_HOME=/tmp/.cache
ENV TORCH_HOME=/tmp/.cache/torch
ENV NUMBA_CACHE_DIR=/tmp/.cache/numba

# Create cache directories
RUN mkdir -p /tmp/.cache/huggingface /tmp/.cache/torch /tmp/.cache/numba

# 1️⃣  app code
COPY rag_module/             ./rag_module/
COPY utils/vector_store.py   utils/logging_config.py   ./utils/
COPY settings_ingest.py      ./
COPY tenants.json            /opt/app/tenants.json

# 2️⃣  deps (modern stack, single line)
RUN pip install --upgrade pip && \
    pip install \
      "PyMuPDF<1.26" pillow \
      openai pinecone>=6 tenacity \
      langchain-openai langchain-pinecone langchain-text-splitters \
      pydantic-settings \
      numpy zstandard orjson regex \
      docling \
      psutil>=6.0.0 \
      boto3>=1.34.0 \
      PyPDF2>=3.0.0

# 3️⃣  Lambda entrypoint
CMD ["rag_module.lambda_entrypoint.handler"]