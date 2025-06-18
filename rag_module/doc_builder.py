# from __future__ import annotations
# from typing import List

# from langchain_core.documents import Document
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_openai import OpenAIEmbeddings
# from langchain_pinecone import PineconeVectorStore

# class DocumentBuilder:

#     def __init__(self, 
#                  pinecone_vs: PineconeVectorStore, 
#                  chunk_size: int = 1000, 
#                  chunk_overlap: int = 100):
#         """
#         Initialize the DocumentBuilder with a Pinecone vector store and text splitter.
#         Args:
#             pinecone_vs (PineconeVectorStore): The Pinecone vector store for storing document embeddings
#             chunk_size (int): Size of text chunks to split documents into
#             chunk_overlap (int): Overlap between text chunks
#             embedder (OpenAIEmbeddings): Embedding model for generating document embeddings
#         """
#         self.splitter = RecursiveCharacterTextSplitter(
#             chunk_size=chunk_size,
#             chunk_overlap=chunk_overlap,
#             length_function=len
#         )
#         self.pinecone_vs = pinecone_vs
#         self.chunk_size = chunk_size
#         self.chunk_overlap = chunk_overlap

#     def build_documents(self, pdoc, captions: List[str]) -> int:
#         caption_text = "\n\n".join(f"[IMAGE] {cap}" for cap in captions)
#         merged_text = f"{pdoc.text_content}\n\n---\n{caption_text}".strip()

#         # Split the merged text into chunks
#         docs: List[Document] = [
#             Document(
#                 page_content=chunk,
#                 metadata={**pdoc.metadata, "chunk": idx}
#             )
#             for idx, chunk in enumerate(self.splitter.split_text(merged_text))
#         ]

#         # Add documents to the Pinecone vector store
#         self.pinecone_vs.add_documents(docs)
#         return len(docs)
"""
doc_builder.py
──────────────
Merge raw text + image captions → chunk → embed → upsert.

Dependencies
------------
• utils.vector_store.get_vector_store  – wraps Pinecone init / index creation
• langchain_text_splitters.RecursiveCharacterTextSplitter
"""

from __future__ import annotations
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


from rag_module.ingest_vector_store import get_vector_store


class DocBuilder:
    def __init__(
        self,
        *,
        index_name: str,
        chunk_size: int = 1_000,
        chunk_overlap: int = 100,
    ) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        # single line does all Pinecone init / embedder wiring
        self.vstore = get_vector_store(index_name)

    # ------------------------------------------------------------------ #
    def build(self, pdoc, captions: List[str]) -> int:
        """
        Parameters
        ----------
        pdoc      : IngestedDoc  (from pdfingestor.py) – must have .text & .s3_key
        captions  : list[str]    – may be empty if no images

        Returns   : int  – number of chunks upserted
        """
        caption_block = "\n\n".join(f"[IMAGE] {c}" for c in captions).strip()
        merged = f"{pdoc.text}\n\n---\n{caption_block}".strip()

        docs = [
            Document(
                page_content=chunk,
                metadata={"source": pdoc.s3_key, "chunk": i},
            )
            for i, chunk in enumerate(self.splitter.split_text(merged))
        ]
        self.vstore.add_documents(docs)
        return len(docs)