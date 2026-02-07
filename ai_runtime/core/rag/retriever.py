from typing import List, Dict, Optional
from abc import ABC, abstractmethod


class Document:
    """Document class for RAG"""

    def __init__(self, content: str, metadata: Optional[Dict] = None, score: float = 0.0):
        self.content = content
        self.metadata = metadata or {}
        self.score = score

    def __repr__(self):
        return f"Document(score={self.score}, content={self.content[:100]}...)"


class VectorStore(ABC):
    """Abstract vector store interface"""

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> List[Document]:
        """Search for similar documents"""
        pass

    @abstractmethod
    async def add_documents(self, documents: List[Document]):
        """Add documents to vector store"""
        pass


class SimpleVectorStore(VectorStore):
    """Simple in-memory vector store (for demo purposes)"""

    def __init__(self):
        self.documents: List[Document] = []

    async def search(self, query: str, top_k: int = 5) -> List[Document]:
        """Simple keyword-based search"""
        query_lower = query.lower()
        results = []

        for doc in self.documents:
            content_lower = doc.content.lower()
            # Simple scoring based on keyword matches
            score = sum(1 for word in query_lower.split() if word in content_lower)
            if score > 0:
                results.append(Document(
                    content=doc.content,
                    metadata=doc.metadata,
                    score=score
                ))

        # Sort by score and return top_k
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def add_documents(self, documents: List[Document]):
        """Add documents to store"""
        self.documents.extend(documents)


class DatabaseVectorStore(VectorStore):
    """Database-backed vector store using knowledge base repository"""

    def __init__(self, kb_service, tenant_id: str, user_id: Optional[str] = None):
        """
        Initialize database vector store

        Args:
            kb_service: KnowledgeBaseService instance
            tenant_id: Tenant ID for multi-tenancy
            user_id: User ID for filtering
        """
        self.kb_service = kb_service
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def search(self, query: str, top_k: int = 5) -> List[Document]:
        """
        Search for similar documents using vector similarity

        Args:
            query: Search query
            top_k: Number of documents to retrieve

        Returns:
            List of documents with similarity scores
        """
        # Use the knowledge base service to search
        results = await self.kb_service.search_documents(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            query=query,
            top_k=top_k,
        )

        # Convert to RAG Document format
        documents = []
        for kb_doc, score in results:
            doc = Document(
                content=kb_doc.content,
                metadata={
                    "id": kb_doc.id,
                    "title": kb_doc.title,
                    "source": kb_doc.source,
                    "source_type": kb_doc.source_type.value,
                    **kb_doc.metadata,
                },
                score=score,
            )
            documents.append(doc)

        return documents

    async def add_documents(self, documents: List[Document]):
        """
        Add documents to the knowledge base

        Note: This requires CreateDocumentRequest objects.
        For RAG integration, documents should be added via the knowledge base API.
        """
        # This is a placeholder - in practice, documents should be added
        # via the knowledge base service create_document method
        raise NotImplementedError(
            "Use KnowledgeBaseService.create_document to add documents"
        )


class Retriever:
    """Document retriever for RAG"""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    async def retrieve(self, query: str, top_k: int = 5) -> List[Document]:
        """
        Retrieve relevant documents for query

        Args:
            query: Search query
            top_k: Number of documents to retrieve

        Returns:
            List of relevant documents
        """
        return await self.vector_store.search(query, top_k)

    async def add_documents(self, documents: List[Document]):
        """Add documents to vector store"""
        await self.vector_store.add_documents(documents)
