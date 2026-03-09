"""
Retrieval Evaluation Service
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from .knowledge_base_service import KnowledgeBaseService, DEFAULT_RETRIEVAL_SETTINGS
from .document_service import DocumentService
from ..repositories.retrieval_evaluation_repository import RetrievalEvaluationRepository


class RetrievalEvaluationService:
    """检索评测业务逻辑"""

    def __init__(
        self,
        repository: RetrievalEvaluationRepository,
        kb_service: KnowledgeBaseService,
        document_service: DocumentService,
    ):
        self.repository = repository
        self.kb_service = kb_service
        self.document_service = document_service

    async def _ensure_kb_access(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> None:
        kb = await self.kb_service.get_knowledge_base(kb_id, tenant_id, user_id)
        if not kb:
            raise ValueError("Knowledge base not found")

    async def _build_document_lookup(
        self,
        tenant_id: str,
        user_id: Optional[str],
        kb_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        docs, _total = await self.document_service.list_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=kb_id,
            page=1,
            page_size=1000,
        )
        return {
            doc.id: {
                "id": doc.id,
                "title": doc.title,
                "source": doc.source,
            }
            for doc in docs
        }

    def _normalize_case(
        self,
        case: Dict[str, Any],
        document_lookup: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        query = str(case.get("query") or "").strip()
        if not query:
            raise ValueError("测试样本 query 不能为空")

        case_id = str(case.get("id") or uuid.uuid4())
        expected_ids: List[str] = []
        for doc_id in case.get("expected_document_ids") or []:
            value = str(doc_id).strip()
            if value and value in document_lookup and value not in expected_ids:
                expected_ids.append(value)

        expected_documents = [document_lookup[doc_id] for doc_id in expected_ids]

        return {
            "id": case_id,
            "query": query,
            "expected_document_ids": expected_ids,
            "expected_documents": expected_documents,
            "notes": str(case.get("notes") or "").strip(),
        }

    async def list_test_sets(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        await self._ensure_kb_access(kb_id, tenant_id, user_id)
        return await self.repository.list_test_sets(tenant_id, kb_id, user_id)

    async def create_test_set(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
        name: str,
        description: Optional[str],
        cases: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        await self._ensure_kb_access(kb_id, tenant_id, user_id)
        document_lookup = await self._build_document_lookup(tenant_id, user_id, kb_id)
        normalized_cases = [self._normalize_case(case, document_lookup) for case in cases]
        if not normalized_cases:
            raise ValueError("测试集至少需要 1 条测试样本")

        return await self.repository.create_test_set(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            user_id=None,
            name=name.strip(),
            description=(description or "").strip() or None,
            cases=normalized_cases,
        )

    async def update_test_set(
        self,
        test_set_id: str,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
        name: str,
        description: Optional[str],
        cases: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        await self._ensure_kb_access(kb_id, tenant_id, user_id)
        document_lookup = await self._build_document_lookup(tenant_id, user_id, kb_id)
        normalized_cases = [self._normalize_case(case, document_lookup) for case in cases]
        if not normalized_cases:
            raise ValueError("测试集至少需要 1 条测试样本")

        return await self.repository.update_test_set(
            test_set_id=test_set_id,
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            user_id=user_id,
            name=name.strip(),
            description=(description or "").strip() or None,
            cases=normalized_cases,
        )

    async def delete_test_set(
        self,
        test_set_id: str,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> bool:
        await self._ensure_kb_access(kb_id, tenant_id, user_id)
        return await self.repository.delete_test_set(test_set_id, tenant_id, kb_id, user_id)

    async def list_runs(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        await self._ensure_kb_access(kb_id, tenant_id, user_id)
        return await self.repository.list_runs(tenant_id, kb_id, user_id, limit)

    async def get_run(
        self,
        run_id: str,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        await self._ensure_kb_access(kb_id, tenant_id, user_id)
        return await self.repository.get_run(run_id, tenant_id, kb_id, user_id)

    def _build_effective_config(
        self,
        current_settings: Dict[str, Any],
        config_override: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = dict(DEFAULT_RETRIEVAL_SETTINGS)
        merged.update(current_settings or {})
        for key, value in (config_override or {}).items():
            if value == "":
                value = None
            if value is not None:
                merged[key] = value
        return merged

    def _summarize_run(
        self,
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        total = len(results)
        hit_count = sum(1 for item in results if item.get("hit"))
        top_hit_count = sum(1 for item in results if item.get("top_hit"))
        manual_scores = [
            float(item["manual_score"])
            for item in results
            if item.get("manual_score") is not None
        ]
        return {
            "total_cases": total,
            "hit_count": hit_count,
            "top_hit_count": top_hit_count,
            "hit_rate": round(hit_count / total, 4) if total else 0.0,
            "top_hit_rate": round(top_hit_count / total, 4) if total else 0.0,
            "avg_manual_score": round(sum(manual_scores) / len(manual_scores), 4) if manual_scores else None,
            "manual_score_count": len(manual_scores),
        }

    async def run_evaluation(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
        test_set_id: str,
        config_override: Dict[str, Any],
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._ensure_kb_access(kb_id, tenant_id, user_id)
        test_set = await self.repository.get_test_set(test_set_id, tenant_id, kb_id, user_id)
        if not test_set:
            raise ValueError("Test set not found")

        current_settings = await self.kb_service.get_retrieval_settings(kb_id, tenant_id, user_id)
        if current_settings is None:
            raise ValueError("Knowledge base not found")

        effective_config = self._build_effective_config(current_settings, config_override)
        run_results: List[Dict[str, Any]] = []

        for case in test_set.get("cases") or []:
            query = str(case.get("query") or "").strip()
            expected_ids = [str(item) for item in case.get("expected_document_ids") or []]

            search_results = await self.document_service.search_documents(
                tenant_id=tenant_id,
                user_id=user_id,
                query=query,
                top_k=int(effective_config.get("top_k") or 5),
                knowledge_base_id=kb_id,
                top_k_override=int(effective_config.get("top_k") or 5),
                score_threshold_override=float(effective_config.get("score_threshold") or 0.0),
                retrieval_method_override=effective_config.get("retrieval_method"),
                enable_rerank_override=effective_config.get("enable_rerank"),
                rerank_model_id_override=effective_config.get("rerank_model_id"),
            )

            result_items = []
            matched_ids = []
            for doc, score in search_results:
                matched_ids.append(doc.id)
                matched_segments = await self.document_service.get_matched_segments(
                    document=doc,
                    query=query,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    max_segments=2,
                )
                result_items.append({
                    "document_id": doc.id,
                    "title": doc.title,
                    "source": doc.source,
                    "score": round(float(score), 4),
                    "matched_segments": matched_segments,
                })

            hit = any(doc_id in matched_ids for doc_id in expected_ids) if expected_ids else False
            top_hit = bool(matched_ids and expected_ids and matched_ids[0] in expected_ids)

            run_results.append({
                "case_id": case.get("id"),
                "query": query,
                "notes": case.get("notes") or "",
                "expected_document_ids": expected_ids,
                "expected_documents": case.get("expected_documents") or [],
                "matched_document_ids": matched_ids,
                "top_result_document_id": matched_ids[0] if matched_ids else None,
                "hit": hit,
                "top_hit": top_hit,
                "manual_score": None,
                "manual_comment": "",
                "results": result_items,
            })

        summary = self._summarize_run(run_results)
        run_name = (name or "").strip() or f"评测 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"

        return await self.repository.create_run(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            test_set_id=test_set_id,
            user_id=None,
            name=run_name,
            config=effective_config,
            summary=summary,
            results=run_results,
            metadata={"test_set_name": test_set.get("name")},
        )

    async def update_run_feedback(
        self,
        run_id: str,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
        case_id: str,
        manual_score: Optional[float],
        manual_comment: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        run = await self.get_run(run_id, kb_id, tenant_id, user_id)
        if not run:
            return None

        results = list(run.get("results") or [])
        updated = False
        for item in results:
            if str(item.get("case_id")) == str(case_id):
                item["manual_score"] = manual_score
                item["manual_comment"] = (manual_comment or "").strip()
                updated = True
                break

        if not updated:
            raise ValueError("Case result not found")

        summary = self._summarize_run(results)
        return await self.repository.update_run(
            run_id=run_id,
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            user_id=user_id,
            summary=summary,
            results=results,
        )

    async def apply_run_config(
        self,
        run_id: str,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        run = await self.get_run(run_id, kb_id, tenant_id, user_id)
        if not run:
            raise ValueError("Evaluation run not found")

        config = dict(run.get("config") or {})
        applied_settings = await self.kb_service.update_retrieval_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            updates=config,
        )
        if applied_settings is None:
            raise ValueError("Knowledge base not found")

        metadata = dict(run.get("metadata") or {})
        metadata["applied_to_production_at"] = datetime.utcnow().isoformat()
        metadata["applied_to_production"] = True
        await self.repository.update_run(
            run_id=run_id,
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            user_id=user_id,
            metadata=metadata,
        )
        return applied_settings
