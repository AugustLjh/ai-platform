from typing import List, Optional
from .retriever import Retriever, Document


class RAGPipeline:
    """RAG pipeline for retrieval-augmented generation"""

    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    async def process(self, query: str, top_k: int = 5) -> str:
        """
        Process query through RAG pipeline

        Args:
            query: User query
            top_k: Number of documents to retrieve

        Returns:
            Formatted context string
        """
        # Retrieve relevant documents
        documents = await self.retriever.retrieve(query, top_k)

        # Format context
        if not documents:
            return ""

        context_parts = []
        for i, doc in enumerate(documents, 1):
            context_parts.append(f"[Document {i}] (Relevance: {doc.score:.2f})")
            context_parts.append(doc.content)
            context_parts.append("")

        return "\n".join(context_parts)

    async def add_documents(self, documents: List[Document]):
        """Add documents to the pipeline"""
        await self.retriever.add_documents(documents)
