"""
Document Service - Business Logic Layer
"""
import hashlib
import logging
import re
from collections import Counter
from datetime import datetime
from uuid import UUID
from typing import List, Optional, Dict, Any
from fastapi import UploadFile

from core.models.knowledge_base import (
    Document,
    SourceType,
    AccessLevel,
    CreateDocumentRequest,
    UpdateDocumentRequest,
)
from core.repositories.document_repository import DocumentRepository
from core.repositories.knowledge_base_repository import KnowledgeBaseRepository
from core.embeddings import EmbeddingService, OpenAIEmbedding, JinaEmbedding, SentenceTransformerEmbedding
from core.config import AppConfig
from core.parsers.file_parser import FileParser
from core.parsers.url_fetcher import URLFetcher
from core.audit import AuditLogger
from core.quota import QuotaManager


logger = logging.getLogger(__name__)


class DuplicateDocumentError(Exception):
    """重复或高相似文档冲突。"""

    def __init__(self, payload: Dict[str, Any]):
        self.payload = payload
        super().__init__(payload.get("message") or "Duplicate document detected")

AI_METADATA_KEYS = {
    "ai_summary",
    "ai_keywords",
    "ai_tags",
    "ai_faq",
    "ai_document_type",
    "ai_processed_at",
    "ai_content_hash",
    "ai_simhash",
    "ai_processing_version",
}

CHINESE_STOPWORDS = {
    "我们", "你们", "他们", "这是", "一个", "一些", "这个", "那个", "以及", "进行",
    "相关", "支持", "使用", "可以", "通过", "需要", "如果", "没有", "已经", "为了",
    "关于", "其中", "功能", "系统", "平台", "文档", "内容", "说明", "问题", "方案",
}

ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "have", "has",
    "are", "was", "were", "will", "shall", "you", "your", "our", "their", "about",
    "document", "system", "platform", "usage", "using", "used", "guide",
}

DEFAULT_INDEXING_SETTINGS = {
    "indexing_method": "chunk",
    "chunk_size": 500,
    "chunk_overlap": 50,
    "embedding_model_id": None,
}

DEFAULT_RETRIEVAL_SETTINGS = {
    "retrieval_method": "vector",
    "top_k": 5,
    "score_threshold": 0.0,
    "enable_rerank": False,
    "rerank_model_id": None,
}

SIMHASH_MAX_DISTANCE = 8
SIMILARITY_LIMIT = 5
CANDIDATE_SCAN_LIMIT = 200


class DocumentService:
    """文档业务逻辑服务"""

    def __init__(
        self,
        repository: DocumentRepository,
        kb_repository: KnowledgeBaseRepository,
        embedding_service: EmbeddingService,
        audit_logger: Optional[AuditLogger] = None,
        quota_manager: Optional[QuotaManager] = None,
    ):
        """
        初始化服务

        Args:
            repository: 文档数据库仓库
            kb_repository: 知识库数据库仓库
            embedding_service: 向量嵌入服务
            audit_logger: 审计日志服务（可选）
            quota_manager: 配额管理服务（可选）
        """
        self.repository = repository
        self.kb_repository = kb_repository
        self.embedding_service = embedding_service
        self.audit_logger = audit_logger
        self.quota_manager = quota_manager
        self.url_fetcher = URLFetcher()
        self._app_config = AppConfig.from_env()
        self._embedding_service_cache: Dict[str, EmbeddingService] = {}

    async def _get_kb_metadata(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
    ) -> Dict[str, Any]:
        if not knowledge_base_id:
            return {}

        kb = await self.kb_repository.get_knowledge_base(
            kb_id=knowledge_base_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            return {}

        return kb.metadata or {}

    def _merge_settings(self, metadata: Dict[str, Any], key: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
        settings = metadata.get(key) if isinstance(metadata.get(key), dict) else {}
        merged = dict(defaults)
        merged.update(settings or {})
        return merged

    async def _get_indexing_settings(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
    ) -> Dict[str, Any]:
        metadata = await self._get_kb_metadata(tenant_id, user_id, knowledge_base_id)
        return self._merge_settings(metadata, "indexing_settings", DEFAULT_INDEXING_SETTINGS)

    async def _get_retrieval_settings(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
    ) -> Dict[str, Any]:
        metadata = await self._get_kb_metadata(tenant_id, user_id, knowledge_base_id)
        return self._merge_settings(metadata, "retrieval_settings", DEFAULT_RETRIEVAL_SETTINGS)

    def _normalize_chunk_settings(self, chunk_size: int, chunk_overlap: int) -> tuple[int, int]:
        if chunk_size <= 0:
            chunk_size = DEFAULT_INDEXING_SETTINGS["chunk_size"]

        if chunk_overlap < 0:
            chunk_overlap = 0

        if chunk_overlap >= chunk_size:
            chunk_overlap = max(0, chunk_size - 1)

        return chunk_size, chunk_overlap

    def _chunk_text_with_offsets(self, text: str, chunk_size: int, chunk_overlap: int) -> List[Dict[str, Any]]:
        chunk_size, chunk_overlap = self._normalize_chunk_settings(chunk_size, chunk_overlap)
        if not text:
            return []

        chunks: List[Dict[str, Any]] = []
        start = 0
        text_length = len(text)
        segment_index = 1

        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_content = text[start:end]
            chunks.append(
                {
                    "segment_index": segment_index,
                    "start_offset": start,
                    "end_offset": end,
                    "char_count": len(chunk_content),
                    "content": chunk_content,
                }
            )
            if end >= text_length:
                break
            start = max(0, end - chunk_overlap)
            segment_index += 1

        return chunks

    def _chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        return [segment["content"] for segment in self._chunk_text_with_offsets(text, chunk_size, chunk_overlap)]

    def _normalize_text_for_ai_processing(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\u3000", " ")
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_sentences(self, text: str) -> List[str]:
        normalized = self._normalize_text_for_ai_processing(text)
        if not normalized:
            return []

        sentences = re.findall(r"[^。！？!?；;\n]+[。！？!?；;.]?|[^\n]+", normalized)
        cleaned: List[str] = []
        for sentence in sentences:
            item = sentence.strip(" -*\t")
            if len(item) >= 8:
                cleaned.append(item)
        return cleaned

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"

    def _generate_ai_summary(self, title: str, text: str, max_chars: int = 180) -> str:
        sentences = self._split_sentences(text)
        summary_parts: List[str] = []
        current_length = 0

        for sentence in sentences[:5]:
            piece = sentence
            extra = 1 if summary_parts else 0
            if current_length + len(piece) + extra > max_chars and summary_parts:
                break
            summary_parts.append(piece)
            current_length += len(piece) + extra
            if current_length >= int(max_chars * 0.7):
                break

        if summary_parts:
            return self._truncate_text(" ".join(summary_parts), max_chars)

        title = (title or "").strip()
        normalized = self._normalize_text_for_ai_processing(text)
        fallback = normalized[:max_chars] if normalized else title
        return self._truncate_text(fallback, max_chars)

    def _extract_candidate_phrases(self, title: str, text: str) -> List[str]:
        candidates: List[str] = []

        title_clean = re.sub(r"[^\w\u4e00-\u9fff-]", "", (title or "").strip())
        if 2 <= len(title_clean) <= 20:
            candidates.extend([title_clean, title_clean])

        for raw_line in self._normalize_text_for_ai_processing(text).splitlines():
            line = raw_line.strip(" -*#\t")
            line = re.sub(r"[^\w\u4e00-\u9fff-]", "", line)
            if 2 <= len(line) <= 16:
                candidates.append(line)

        segments = re.split(r"[，。！？；：,.!?:;\n/()（）\[\]【】]+", text)
        for segment in segments:
            phrase = re.sub(r"[^\w\u4e00-\u9fff-]", "", segment.strip())
            if 2 <= len(phrase) <= 12:
                candidates.append(phrase)

        return candidates

    def _extract_keywords(self, title: str, text: str, limit: int = 8) -> List[str]:
        counter: Counter[str] = Counter()

        for phrase in self._extract_candidate_phrases(title, text):
            if re.search(r"[\u4e00-\u9fff]", phrase):
                if phrase in CHINESE_STOPWORDS:
                    continue
                counter[phrase] += 1
            elif re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{2,30}", phrase):
                lower_phrase = phrase.lower()
                if lower_phrase in ENGLISH_STOPWORDS:
                    continue
                counter[phrase] += 1

        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,30}", text):
            lower_token = token.lower()
            if lower_token not in ENGLISH_STOPWORDS:
                counter[token] += 1

        keywords: List[str] = []
        for item, _count in counter.most_common(limit * 3):
            if item not in keywords:
                keywords.append(item)
            if len(keywords) >= limit:
                break

        return keywords

    def _detect_document_type(
        self,
        title: str,
        text: str,
        source: Optional[str],
        source_type: SourceType,
    ) -> str:
        haystack = f"{title}\n{text[:2000]}\n{source or ''}".lower()

        patterns = [
            ("API 文档", ("api", "endpoint", "请求参数", "响应参数", "curl", "鉴权")),
            ("FAQ", ("faq", "常见问题", "q:", "a:", "问题解答")),
            ("操作指南", ("安装", "部署", "步骤", "使用说明", "快速开始", "教程")),
            ("设计方案", ("架构", "设计", "方案", "流程图", "模块设计")),
            ("报告分析", ("报告", "分析", "复盘", "总结", "洞察")),
            ("规范制度", ("规范", "标准", "制度", "要求", "约定")),
        ]

        for label, markers in patterns:
            if any(marker in haystack for marker in markers):
                return label

        source_value = (source or "").lower()
        if source_type == SourceType.URL:
            return "网页资料"
        if source_value.endswith((".xlsx", ".csv", ".tsv")):
            return "数据表"
        if source_value.endswith((".ppt", ".pptx")):
            return "演示材料"
        if source_value.endswith((".pdf", ".doc", ".docx")):
            return "正式文档"
        if source_value.endswith((".md", ".txt", ".log")):
            return "文本资料"

        return "综合文本"

    def _build_simhash(self, values: List[str], bits: int = 64) -> str:
        if not values:
            return ""

        vector = [0] * bits
        for value in values:
            digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
            hashed = int(digest[:16], 16)
            weight = 2 if len(value) >= 4 else 1
            for bit_index in range(bits):
                bitmask = 1 << bit_index
                vector[bit_index] += weight if hashed & bitmask else -weight

        signature = 0
        for bit_index, score in enumerate(vector):
            if score >= 0:
                signature |= 1 << bit_index

        return f"{signature:016x}"

    def _generate_faq(
        self,
        summary: str,
        keywords: List[str],
        document_type: str,
        text: str,
    ) -> List[Dict[str, str]]:
        faq: List[Dict[str, str]] = []
        sentences = self._split_sentences(text)

        if summary:
            faq.append({
                "question": "这份文档主要讲什么？",
                "answer": summary,
            })

        if keywords:
            faq.append({
                "question": "文档涉及哪些关键主题？",
                "answer": "、".join(keywords[:5]),
            })

        if document_type:
            faq.append({
                "question": "这份文档属于什么类型？",
                "answer": f"这是一份{document_type}。",
            })

        if sentences:
            faq.append({
                "question": "优先应该关注哪部分内容？",
                "answer": self._truncate_text(sentences[0], 120),
            })

        return faq[:4]

    def _build_ai_metadata(
        self,
        title: str,
        content: str,
        source: Optional[str],
        source_type: SourceType,
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_content = self._normalize_text_for_ai_processing(content)
        merged_metadata = dict(base_metadata or {})
        for key in AI_METADATA_KEYS:
            merged_metadata.pop(key, None)

        summary = self._generate_ai_summary(title, normalized_content)
        keywords = self._extract_keywords(title, normalized_content)
        document_type = self._detect_document_type(title, normalized_content, source, source_type)
        faq = self._generate_faq(summary, keywords, document_type, normalized_content)
        content_hash = hashlib.sha1(normalized_content.encode("utf-8")).hexdigest() if normalized_content else ""
        simhash = self._build_simhash(keywords or self._extract_candidate_phrases(title, normalized_content))

        merged_metadata.update({
            "ai_summary": summary,
            "ai_keywords": keywords,
            "ai_tags": keywords[:5],
            "ai_faq": faq,
            "ai_document_type": document_type,
            "ai_processed_at": datetime.utcnow().isoformat(),
            "ai_content_hash": content_hash,
            "ai_simhash": simhash,
            "ai_processing_version": "p1-v1",
        })
        return merged_metadata

    def _normalize_duplicate_compare_value(self, value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", "", value).strip().lower()

    def _simhash_distance(self, left: str, right: str) -> Optional[int]:
        if not left or not right:
            return None

        try:
            left_value = int(left, 16)
            right_value = int(right, 16)
        except ValueError:
            return None

        return (left_value ^ right_value).bit_count()

    def _build_duplicate_match(
        self,
        document: Document,
        match_type: str,
        reason: str,
        similarity: Optional[float] = None,
        distance: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload = {
            "id": document.id,
            "title": document.title,
            "source": document.source,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "match_type": match_type,
            "reason": reason,
        }
        if similarity is not None:
            payload["similarity"] = round(similarity, 3)
        if distance is not None:
            payload["simhash_distance"] = distance
        return payload

    def _extract_duplicate_signature(
        self,
        document: Document,
    ) -> tuple[str, str]:
        metadata = dict(document.metadata or {})
        content_hash = metadata.get("ai_content_hash")
        simhash = metadata.get("ai_simhash")

        if content_hash and simhash:
            return str(content_hash), str(simhash)

        try:
            derived_metadata = self._build_ai_metadata(
                title=document.title,
                content=document.content,
                source=document.source,
                source_type=document.source_type,
                base_metadata=metadata,
            )
            return (
                str(derived_metadata.get("ai_content_hash") or ""),
                str(derived_metadata.get("ai_simhash") or ""),
            )
        except Exception as exc:
            logger.error(f"Failed to derive duplicate signature for document {document.id}: {exc}")
            return "", ""

    async def _ensure_no_duplicate_document(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: str,
        title: str,
        content: str,
        source: Optional[str],
        source_type: SourceType,
    ) -> None:
        metadata = self._build_ai_metadata(
            title=title,
            content=content,
            source=source,
            source_type=source_type,
        )
        content_hash = str(metadata.get("ai_content_hash") or "")
        simhash = str(metadata.get("ai_simhash") or "")
        normalized_title = self._normalize_duplicate_compare_value(title)
        normalized_source = self._normalize_duplicate_compare_value(source)

        exact_matches = [
            self._build_duplicate_match(
                document=doc,
                match_type="exact",
                reason="same_content",
                similarity=1.0,
                distance=0,
            )
            for doc in await self.repository.find_exact_duplicate_documents(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                content_hash=content_hash,
                content=content,
                user_id=user_id,
                limit=SIMILARITY_LIMIT,
            )
        ]

        exact_match_ids = {item["id"] for item in exact_matches}
        similar_matches: List[Dict[str, Any]] = []

        for candidate in await self.repository.list_documents_for_duplicate_check(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            limit=CANDIDATE_SCAN_LIMIT,
        ):
            if candidate.id in exact_match_ids:
                continue

            candidate_hash, candidate_simhash = self._extract_duplicate_signature(candidate)
            if content_hash and candidate_hash and candidate_hash == content_hash:
                exact_matches.append(
                    self._build_duplicate_match(
                        document=candidate,
                        match_type="exact",
                        reason="same_content_hash",
                        similarity=1.0,
                        distance=0,
                    )
                )
                exact_match_ids.add(candidate.id)
                continue

            distance = self._simhash_distance(simhash, candidate_simhash)
            if distance is None:
                continue

            similarity = 1 - (distance / 64)
            candidate_title = self._normalize_duplicate_compare_value(candidate.title)
            candidate_source = self._normalize_duplicate_compare_value(candidate.source)
            same_name = normalized_title and normalized_title == candidate_title
            same_source = normalized_source and normalized_source == candidate_source

            if distance > SIMHASH_MAX_DISTANCE and not ((same_name or same_source) and similarity >= 0.8):
                continue

            reason = "similar_content"
            if same_name and same_source:
                reason = "same_name_and_source"
            elif same_name:
                reason = "same_name_similar_content"
            elif same_source:
                reason = "same_source_similar_content"

            similar_matches.append(
                self._build_duplicate_match(
                    document=candidate,
                    match_type="similar",
                    reason=reason,
                    similarity=similarity,
                    distance=distance,
                )
            )

        unique_exact_matches = list({item["id"]: item for item in exact_matches}.values())
        similar_matches.sort(
            key=lambda item: (
                item.get("similarity", 0.0),
                item.get("updated_at") or "",
            ),
            reverse=True,
        )
        unique_similar_matches = []
        seen_similar_ids = set()
        for item in similar_matches:
            if item["id"] in seen_similar_ids or item["id"] in exact_match_ids:
                continue
            seen_similar_ids.add(item["id"])
            unique_similar_matches.append(item)
            if len(unique_similar_matches) >= SIMILARITY_LIMIT:
                break

        if unique_exact_matches or unique_similar_matches:
            raise DuplicateDocumentError({
                "code": "duplicate_document_detected",
                "message": "发现重复或高相似文档，请确认是否继续上传。",
                "duplicate_check": {
                    "exact_matches": unique_exact_matches[:SIMILARITY_LIMIT],
                    "similar_matches": unique_similar_matches,
                    "can_force_upload": True,
                },
            })

    def _average_embeddings(self, embeddings: List[List[float]]) -> List[float]:
        if not embeddings:
            return []
        length = len(embeddings[0])
        sums = [0.0] * length
        for emb in embeddings:
            for idx, value in enumerate(emb):
                sums[idx] += value
        return [value / len(embeddings) for value in sums]

    async def _get_embedding_service_for_model(
        self,
        tenant_id: str,
        model_id: Optional[str],
    ) -> Optional[EmbeddingService]:
        if not model_id:
            return None

        if model_id in self._embedding_service_cache:
            return self._embedding_service_cache[model_id]

        query = """
            SELECT provider, model_id, api_base, api_key_encrypted
            FROM llm_models
            WHERE id = $1
              AND model_type = 'embedding'
              AND (tenant_id = $2 OR tenant_id IS NULL)
              AND enabled = true
        """

        try:
            model_uuid = UUID(model_id)
        except ValueError:
            logger.warning(f"Invalid embedding model id: {model_id}")
            return None

        async with self.repository.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, model_uuid, tenant_id)

        if not row:
            return None

        provider = row['provider']
        model_name = row['model_id']
        api_base = row['api_base']
        api_key = row['api_key_encrypted']

        service: Optional[EmbeddingService] = None

        try:
            if provider == "openai":
                if not api_key:
                    raise ValueError("Missing API key for OpenAI embedding model")
                service = OpenAIEmbedding(
                    api_key=api_key,
                    model_name=model_name,
                    api_base=api_base,
                )
            elif provider == "jina":
                if not api_key:
                    raise ValueError("Missing API key for Jina embedding model")
                service = JinaEmbedding(
                    api_key=api_key,
                    model_name=model_name,
                    api_base=api_base,
                )
            elif provider == "local":
                service = SentenceTransformerEmbedding(
                    model_name=model_name,
                    device=self._app_config.embedding.device,
                    cache_folder=self._app_config.embedding.cache_folder,
                )
            else:
                logger.warning(f"Unsupported embedding provider: {provider}")
                return None
        except Exception as exc:
            logger.error(f"Failed to initialize embedding model {model_id}: {exc}")
            return None

        if service:
            self._embedding_service_cache[model_id] = service
        return service

    async def _select_embedding_service(
        self,
        tenant_id: str,
        model_id: Optional[str],
    ) -> EmbeddingService:
        service = await self._get_embedding_service_for_model(tenant_id, model_id)
        return service or self.embedding_service

    async def _build_embedding(
        self,
        content: str,
        embedding_service: EmbeddingService,
        indexing_settings: Dict[str, Any],
    ) -> List[float]:
        method = indexing_settings.get("indexing_method") or "chunk"
        if method == "full":
            return await embedding_service.embed_text(content)

        chunk_size = int(indexing_settings.get("chunk_size") or 500)
        chunk_overlap = int(indexing_settings.get("chunk_overlap") or 50)
        chunks = self._chunk_text(content, chunk_size, chunk_overlap)

        if len(chunks) == 1:
            return await embedding_service.embed_text(chunks[0])

        embeddings = await embedding_service.embed_batch(chunks)
        return self._average_embeddings(embeddings)

    def _merge_results(
        self,
        vector_results: List[tuple[Document, float]],
        keyword_results: List[tuple[Document, float]],
        top_k: int,
    ) -> List[tuple[Document, float]]:
        combined: Dict[str, tuple[Document, float]] = {}

        for doc, score in vector_results:
            combined[doc.id] = (doc, score)

        for doc, score in keyword_results:
            if doc.id in combined:
                existing_doc, existing_score = combined[doc.id]
                combined_score = max(existing_score, score * 0.8)
                combined[doc.id] = (existing_doc, combined_score)
            else:
                combined[doc.id] = (doc, score * 0.8)

        merged = list(combined.values())
        merged.sort(key=lambda item: item[1], reverse=True)
        return merged[:top_k]

    def _apply_rerank(
        self,
        results: List[tuple[Document, float]],
        query: str,
    ) -> List[tuple[Document, float]]:
        if not results:
            return results

        terms = [term for term in query.lower().split() if term]
        if not terms:
            return results

        rescored = []
        for doc, score in results:
            text = f"{doc.title} {doc.content}".lower()
            occurrences = sum(text.count(term) for term in terms)
            boost = min(0.2, occurrences * 0.02)
            rescored.append((doc, min(score + boost, 1.0)))

        rescored.sort(key=lambda item: item[1], reverse=True)
        return rescored

    async def get_document_preview(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        max_chars: int = 4000,
    ) -> Optional[Dict[str, Any]]:
        doc = await self.repository.get_document(document_id, tenant_id, user_id)
        if not doc:
            return None

        total_chars = len(doc.content or "")
        preview_chars = max(1, min(max_chars, 20000))
        truncated = total_chars > preview_chars

        return {
            "document_id": doc.id,
            "title": doc.title,
            "source": doc.source,
            "total_chars": total_chars,
            "preview_chars": preview_chars,
            "truncated": truncated,
            "preview": (doc.content or "")[:preview_chars],
            "indexed": doc.indexed,
            "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
            "updated_at": doc.updated_at.isoformat(),
        }

    async def get_document_segments(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        max_segments: int = 200,
    ) -> Optional[Dict[str, Any]]:
        doc = await self.repository.get_document(document_id, tenant_id, user_id)
        if not doc:
            return None

        if chunk_size is None or chunk_overlap is None:
            indexing_settings = await self._get_indexing_settings(
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=doc.knowledge_base_id,
            )
            if chunk_size is None:
                chunk_size = int(indexing_settings.get("chunk_size") or DEFAULT_INDEXING_SETTINGS["chunk_size"])
            if chunk_overlap is None:
                chunk_overlap = int(indexing_settings.get("chunk_overlap") or DEFAULT_INDEXING_SETTINGS["chunk_overlap"])

        safe_chunk_size, safe_chunk_overlap = self._normalize_chunk_settings(int(chunk_size), int(chunk_overlap))
        segments = self._chunk_text_with_offsets(doc.content or "", safe_chunk_size, safe_chunk_overlap)

        safe_max_segments = max(1, min(max_segments, 1000))
        returned_segments = segments[:safe_max_segments]

        return {
            "document_id": doc.id,
            "title": doc.title,
            "chunk_size": safe_chunk_size,
            "chunk_overlap": safe_chunk_overlap,
            "total_segments": len(segments),
            "returned_segments": len(returned_segments),
            "truncated": len(segments) > len(returned_segments),
            "segments": returned_segments,
        }

    async def get_matched_segments(
        self,
        document: Document,
        query: str,
        tenant_id: str,
        user_id: Optional[str],
        max_segments: int = 3,
    ) -> List[Dict[str, Any]]:
        indexing_settings = await self._get_indexing_settings(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=document.knowledge_base_id,
        )
        chunk_size = int(indexing_settings.get("chunk_size") or DEFAULT_INDEXING_SETTINGS["chunk_size"])
        chunk_overlap = int(indexing_settings.get("chunk_overlap") or DEFAULT_INDEXING_SETTINGS["chunk_overlap"])
        segments = self._chunk_text_with_offsets(document.content or "", chunk_size, chunk_overlap)

        if not segments:
            return []

        terms = [term.strip().lower() for term in query.split() if term.strip()]
        scored_segments: List[Dict[str, Any]] = []

        for segment in segments:
            content_lower = segment["content"].lower()
            occurrences = sum(content_lower.count(term) for term in terms) if terms else 0
            if occurrences > 0:
                segment_with_score = dict(segment)
                segment_with_score["match_score"] = float(occurrences)
                scored_segments.append(segment_with_score)

        if not scored_segments:
            fallback = dict(segments[0])
            fallback["match_score"] = 0.0
            return [fallback]

        scored_segments.sort(key=lambda item: (item["match_score"], -item["segment_index"]), reverse=True)
        return scored_segments[:max(1, min(max_segments, 10))]

    async def create_document(
        self,
        tenant_id: str,
        user_id: Optional[str],
        request: CreateDocumentRequest,
        context: Optional[Dict[str, Any]] = None,
    ) -> Document:
        """
        创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            request: 创建请求
            context: 请求上下文（用于审计日志）

        Returns:
            创建的文档对象
        """
        # 验证知识库存在且用户有权限访问
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=request.knowledge_base_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            raise ValueError(f"Knowledge base {request.knowledge_base_id} not found or access denied")

        if not request.skip_duplicate_check:
            try:
                await self._ensure_no_duplicate_document(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    knowledge_base_id=request.knowledge_base_id,
                    title=request.title,
                    content=request.content,
                    source=request.source,
                    source_type=request.source_type,
                )
            except DuplicateDocumentError:
                raise
            except Exception as exc:
                logger.error(f"Failed to run duplicate detection: {exc}")

        # 检查配额
        if self.quota_manager:
            await self.quota_manager.check_document_quota(tenant_id)
            await self.quota_manager.check_document_size(request.content)

        # 生成向量嵌入
        embedding = None
        embedding_model = None
        merged_metadata = dict(request.metadata or {})

        try:
            merged_metadata = self._build_ai_metadata(
                title=request.title,
                content=request.content,
                source=request.source,
                source_type=request.source_type,
                base_metadata=merged_metadata,
            )
        except Exception as exc:
            logger.error(f"Failed to generate AI metadata: {exc}")

        if request.auto_index:
            try:
                indexing_settings = await self._get_indexing_settings(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    knowledge_base_id=request.knowledge_base_id,
                )
                embedding_service = await self._select_embedding_service(
                    tenant_id=tenant_id,
                    model_id=indexing_settings.get("embedding_model_id"),
                )
                embedding = await self._build_embedding(
                    request.content,
                    embedding_service,
                    indexing_settings,
                )
                embedding_model = embedding_service.get_model_name()
            except Exception as e:
                logger.error(f"Failed to generate embedding: {e}")
                # 继续创建文档，但标记为未索引

        # 创建文档
        doc = await self.repository.create_document(
            tenant_id=tenant_id,
            user_id=user_id if request.access_level == AccessLevel.USER else None,
            knowledge_base_id=request.knowledge_base_id,
            access_level=request.access_level,
            title=request.title,
            content=request.content,
            source=request.source,
            source_type=request.source_type,
            embedding=embedding,
            embedding_model=embedding_model,
            metadata=merged_metadata,
        )

        # 审计日志
        if self.audit_logger:
            await self.audit_logger.log_document_create(
                document_id=doc.id,
                tenant_id=tenant_id,
                user_id=user_id,
                title=request.title,
                source_type=request.source_type.value,
                ip_address=context.get("ip_address") if context else None,
                user_agent=context.get("user_agent") if context else None,
            )

        # 更新配额追踪
        if self.quota_manager:
            await self.quota_manager.update_quota_tracking(tenant_id)

        return doc

    async def get_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> Optional[Document]:
        """获取文档"""
        return await self.repository.get_document(document_id, tenant_id, user_id)

    async def update_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        request: UpdateDocumentRequest,
    ) -> Optional[Document]:
        """
        更新文档

        Args:
            document_id: 文档ID
            tenant_id: 租户ID
            user_id: 用户ID
            request: 更新请求

        Returns:
            更新后的文档，如果不存在或无权限则返回None
        """
        existing_doc = None
        metadata_to_update = request.metadata

        if request.content is not None or request.metadata is not None or request.re_index:
            existing_doc = await self.repository.get_document(document_id, tenant_id, user_id)
            if not existing_doc:
                return None

        if existing_doc and (request.content is not None or request.metadata is not None):
            base_metadata = dict(existing_doc.metadata or {})
            if request.metadata is not None:
                for key, value in request.metadata.items():
                    base_metadata[key] = value

            effective_title = request.title if request.title is not None else existing_doc.title
            effective_content = request.content if request.content is not None else existing_doc.content
            effective_source = request.source if request.source is not None else existing_doc.source

            try:
                metadata_to_update = self._build_ai_metadata(
                    title=effective_title,
                    content=effective_content,
                    source=effective_source,
                    source_type=existing_doc.source_type,
                    base_metadata=base_metadata,
                )
            except Exception as exc:
                logger.error(f"Failed to refresh AI metadata: {exc}")
                metadata_to_update = base_metadata

        # 如果内容更新且需要重新索引
        embedding = None
        embedding_model = None

        if request.re_index:
            try:
                if existing_doc:
                    content = request.content if request.content is not None else existing_doc.content
                    indexing_settings = await self._get_indexing_settings(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        knowledge_base_id=existing_doc.knowledge_base_id,
                    )
                    embedding_service = await self._select_embedding_service(
                        tenant_id=tenant_id,
                        model_id=indexing_settings.get("embedding_model_id"),
                    )
                    embedding = await self._build_embedding(
                        content,
                        embedding_service,
                        indexing_settings,
                    )
                    embedding_model = embedding_service.get_model_name()
            except Exception as e:
                logger.error(f"Failed to generate embedding: {e}")

        return await self.repository.update_document(
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title=request.title,
            content=request.content,
            source=request.source,
            metadata=metadata_to_update,
            embedding=embedding,
            embedding_model=embedding_model,
        )

    async def delete_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> bool:
        """删除文档"""
        return await self.repository.delete_document(document_id, tenant_id, user_id)

    async def list_documents(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Document], int]:
        """列出文档（分页，可选筛选知识库）"""
        return await self.repository.list_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            access_level=access_level,
            source_type=source_type,
            page=page,
            page_size=page_size,
        )

    async def search_documents(
        self,
        tenant_id: str,
        user_id: Optional[str],
        query: str,
        top_k: int = 5,
        knowledge_base_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
        top_k_override: Optional[int] = None,
        score_threshold_override: Optional[float] = None,
        retrieval_method_override: Optional[str] = None,
        enable_rerank_override: Optional[bool] = None,
        rerank_model_id_override: Optional[str] = None,
    ) -> List[tuple[Document, float]]:
        """
        搜索文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            query: 搜索查询
            top_k: 返回结果数量
            access_level: 筛选访问级别
            source_type: 筛选来源类型

        Returns:
            [(文档, 相似度分数), ...]
        """
        retrieval_settings = None
        if knowledge_base_id:
            retrieval_settings = await self._get_retrieval_settings(
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
            )

        if retrieval_settings:
            retrieval_method = retrieval_method_override or retrieval_settings.get("retrieval_method") or "vector"
            if retrieval_method not in ("vector", "keyword", "hybrid"):
                retrieval_method = "vector"
            effective_top_k = int(top_k_override or retrieval_settings.get("top_k") or top_k)
            score_threshold = float(
                score_threshold_override
                if score_threshold_override is not None
                else retrieval_settings.get("score_threshold") or 0.0
            )
            enable_rerank = (
                bool(enable_rerank_override)
                if enable_rerank_override is not None
                else bool(retrieval_settings.get("enable_rerank"))
            )
            rerank_model_id = rerank_model_id_override or retrieval_settings.get("rerank_model_id")
        else:
            retrieval_method = retrieval_method_override or "vector"
            effective_top_k = int(top_k_override or top_k)
            score_threshold = float(score_threshold_override if score_threshold_override is not None else 0.0)
            enable_rerank = bool(enable_rerank_override) if enable_rerank_override is not None else False
            rerank_model_id = rerank_model_id_override

        results: List[tuple[Document, float]] = []

        if retrieval_method == "keyword":
            results = await self.repository.search_by_keyword(
                tenant_id=tenant_id,
                query=query,
                user_id=user_id,
                top_k=effective_top_k,
                knowledge_base_id=knowledge_base_id,
                access_level=access_level,
                source_type=source_type,
            )
        elif retrieval_method == "hybrid":
            indexing_settings = await self._get_indexing_settings(
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
            )
            embedding_service = await self._select_embedding_service(
                tenant_id=tenant_id,
                model_id=indexing_settings.get("embedding_model_id"),
            )
            query_embedding = await embedding_service.embed_text(query)
            vector_results = await self.repository.search_by_embedding(
                tenant_id=tenant_id,
                query_embedding=query_embedding,
                user_id=user_id,
                top_k=effective_top_k,
                knowledge_base_id=knowledge_base_id,
                access_level=access_level,
                source_type=source_type,
            )
            keyword_results = await self.repository.search_by_keyword(
                tenant_id=tenant_id,
                query=query,
                user_id=user_id,
                top_k=effective_top_k,
                knowledge_base_id=knowledge_base_id,
                access_level=access_level,
                source_type=source_type,
            )
            results = self._merge_results(vector_results, keyword_results, effective_top_k)
        else:
            indexing_settings = await self._get_indexing_settings(
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
            )
            embedding_service = await self._select_embedding_service(
                tenant_id=tenant_id,
                model_id=indexing_settings.get("embedding_model_id"),
            )
            query_embedding = await embedding_service.embed_text(query)
            results = await self.repository.search_by_embedding(
                tenant_id=tenant_id,
                query_embedding=query_embedding,
                user_id=user_id,
                top_k=effective_top_k,
                knowledge_base_id=knowledge_base_id,
                access_level=access_level,
                source_type=source_type,
            )

        if score_threshold and score_threshold > 0:
            results = [(doc, score) for doc, score in results if score >= score_threshold]

        if enable_rerank and rerank_model_id:
            results = self._apply_rerank(results, query)

        return results

    async def upload_file(
        self,
        tenant_id: str,
        user_id: Optional[str],
        file: UploadFile,
        knowledge_base_id: str,
        access_level: AccessLevel = AccessLevel.TENANT,
        auto_index: bool = True,
        skip_duplicate_check: bool = False,
    ) -> Document:
        """
        上传文件并创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            file: 上传的文件
            knowledge_base_id: 所属知识库ID
            access_level: 访问级别
            auto_index: 是否自动索引

        Returns:
            创建的文档对象

        Raises:
            ValueError: 文件类型不支持或解析失败
        """
        # 检查文件类型
        if not FileParser.is_supported(file.filename):
            raise ValueError(
                f"Unsupported file type: {file.filename}. "
                f"Supported: .txt, .text, .log, .md, .markdown, .pdf, .html, .htm, "
                f".csv, .tsv, .json, .jsonl, .yaml, .yml, .xml, .rtf, "
                f".docx, .pptx, .xlsx"
            )

        # 读取文件内容
        file_content = await file.read()

        # 解析文件
        parser = FileParser.get_parser(file.filename)
        try:
            parsed_content = await parser.parse(file_content, file.filename)
        except ImportError as e:
            raise ValueError(str(e))

        if not parsed_content.strip():
            raise ValueError("File content is empty after parsing")

        # 使用文件名作为标题（去除扩展名）
        import os
        title = os.path.splitext(file.filename)[0]

        # 创建文档
        request = CreateDocumentRequest(
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=parsed_content,
            source=file.filename,
            source_type=SourceType.FILE,
            access_level=access_level,
            auto_index=auto_index,
            skip_duplicate_check=skip_duplicate_check,
            metadata={
                "file_size": len(file_content),
                "file_type": file.content_type,
            }
        )

        return await self.create_document(tenant_id, user_id, request)

    async def create_from_url(
        self,
        tenant_id: str,
        user_id: Optional[str],
        url: str,
        knowledge_base_id: str,
        access_level: AccessLevel = AccessLevel.TENANT,
        auto_index: bool = True,
        skip_duplicate_check: bool = False,
    ) -> Document:
        """
        从URL抓取内容并创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            url: 目标URL
            knowledge_base_id: 所属知识库ID
            access_level: 访问级别
            auto_index: 是否自动索引

        Returns:
            创建的文档对象

        Raises:
            ValueError: URL抓取失败
        """
        # 抓取URL内容
        content, title = await self.url_fetcher.fetch_text(url)

        if not content.strip():
            raise ValueError("No content extracted from URL")

        # 创建文档
        request = CreateDocumentRequest(
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=content,
            source=url,
            source_type=SourceType.URL,
            access_level=access_level,
            auto_index=auto_index,
            skip_duplicate_check=skip_duplicate_check,
            metadata={"url": url}
        )

        return await self.create_document(tenant_id, user_id, request)

    async def batch_create_documents(
        self,
        tenant_id: str,
        user_id: Optional[str],
        requests: List[CreateDocumentRequest],
    ) -> List[Dict[str, Any]]:
        """
        批量创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            requests: 创建请求列表

        Returns:
            结果列表，每项包含：{"index": int, "success": bool, "id": str, "error": str}
        """
        results = []

        for idx, request in enumerate(requests):
            try:
                doc = await self.create_document(tenant_id, user_id, request)
                results.append({
                    "index": idx,
                    "success": True,
                    "id": doc.id,
                    "error": None,
                })
            except Exception as e:
                logger.error(f"Failed to create document at index {idx}: {e}")
                results.append({
                    "index": idx,
                    "success": False,
                    "id": None,
                    "error": str(e),
                })

        return results
