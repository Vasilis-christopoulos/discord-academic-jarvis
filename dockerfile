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

# 1️⃣  app code - only files needed for embedding Lambda
COPY rag_module/lambda_entrypoint.py     ./rag_module/
COPY rag_module/pdfingestor.py          ./rag_module/
COPY rag_module/vision_captioner.py     ./rag_module/
COPY rag_module/doc_builder.py          ./rag_module/
COPY rag_module/ingest_vector_store.py  ./rag_module/
COPY rag_module/__init__.py             ./rag_module/

# Copy only required utils
COPY utils/logging_config.py            ./utils/
COPY utils/__init__.py                  ./utils/

# Copy settings and config
COPY settings_ingest.py                 ./
COPY tenants.json                       /opt/app/tenants.json

# 2️⃣  deps (optimized for embedding Lambda only)
RUN pip install --upgrade pip && \
    pip install \
      pillow \
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