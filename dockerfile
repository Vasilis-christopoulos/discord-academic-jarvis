FROM public.ecr.aws/lambda/python:3.10

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
       numpy zstandard orjson regex

# 3️⃣  Lambda entrypoint
CMD ["rag_module.lambda_entrypoint.handler"]