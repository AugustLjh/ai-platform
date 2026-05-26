"""
LLM Models Management API
Provides endpoints for managing LLM model configurations
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from collections.abc import Mapping
from uuid import UUID
import json
import logging

from ai_runtime.core.llm import SUPPORTED_LLM_PROVIDER_PATTERN
from ai_runtime.core.llm.adapters import adapter_schema
from ai_runtime.core.llm.catalog import model_capability_schema
from ai_runtime.core.llm.messages import capability_profile_from_settings, supports_endpoint_protocol
from ai_runtime.core.dependencies import get_db_manager, get_current_tenant_id, get_current_user_id
from ai_runtime.core.database import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["models"])


def _deserialize_config(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            config = json.loads(value)
            return _normalize_model_config(config)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(f"Failed to parse model config JSON: {exc}")
            return {}
    if isinstance(value, Mapping):
        return _normalize_model_config(dict(value))
    return {}


def _serialize_config(value: Any) -> str:
    if value is None:
        return json.dumps({})
    if isinstance(value, str):
        return value
    try:
        return json.dumps(_normalize_model_config(value))
    except TypeError:
        return json.dumps({})


def _normalize_modalities(value: Any, fallback: list[str]) -> list[str]:
    if value is None:
        return list(fallback)
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        items = [value]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized or list(fallback)


def _normalize_model_config(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    config = dict(value)
    config["task_type"] = "chat.completion"
    config["endpoint_protocol"] = str(config.get("endpoint_protocol") or "").strip() or None
    config["input_modalities"] = _normalize_modalities(config.get("input_modalities"), ["text"])
    config["output_modalities"] = ["text"]
    constraints = config.get("constraints")
    adapter_options = config.get("adapter_options")
    config["constraints"] = dict(constraints) if isinstance(constraints, Mapping) else {}
    config["adapter_options"] = dict(adapter_options) if isinstance(adapter_options, Mapping) else {}
    capabilities = capability_profile_from_settings(
        config.get("capabilities") if isinstance(config.get("capabilities"), Mapping) else None,
        {
            "task_type": config.get("task_type"),
            "endpoint_protocol": config.get("endpoint_protocol"),
            "input_modalities": config.get("input_modalities"),
            "output_modalities": config.get("output_modalities"),
            "default_output_modalities": ["text"],
            "supported_response_formats": config.get("supported_response_formats", ["text"]),
            "supports_tools": bool(config.get("supports_tools", False)),
            "supports_streaming": bool(config.get("supports_streaming", True)),
            "supports_reasoning": bool(config.get("supports_reasoning", False)),
            "supports_vision": bool(config.get("supports_vision", False)),
            "supports_audio_input": bool(config.get("supports_audio_input", False)),
            "supports_audio_output": bool(config.get("supports_audio_output", False)),
            "supports_video_input": bool(config.get("supports_video_input", False)),
            "supports_file_input": bool(config.get("supports_file_input", False)),
            "context_window": config.get("context_window"),
            "max_output_tokens": config.get("max_output_tokens"),
            "adapter_options": config.get("adapter_options"),
        },
    )
    config["capabilities"] = capabilities.model_dump()
    config["task_type"] = capabilities.task_type
    config["endpoint_protocol"] = capabilities.endpoint_protocol or config.get("endpoint_protocol")
    config["input_modalities"] = capabilities.input_modalities
    config["output_modalities"] = ["text"]
    config["default_output_modalities"] = ["text"]
    config["supported_response_formats"] = capabilities.supported_response_formats
    config["adapter_options"] = capabilities.adapter_options or config["adapter_options"]
    config["supports_vision"] = capabilities.supports_vision
    config["supports_audio_input"] = capabilities.supports_audio_input
    config["supports_audio_output"] = capabilities.supports_audio_output
    config["supports_video_input"] = capabilities.supports_video_input
    config["supports_file_input"] = capabilities.supports_file_input
    if config["output_modalities"] != ["text"]:
        config["output_modalities"] = ["text"]
    if config["task_type"] != "chat.completion":
        config["task_type"] = "chat.completion"
    return config


# Request/Response Models
class LLMModelConfig(BaseModel):
    """LLM model configuration"""
    task_type: str = "chat.completion"
    endpoint_protocol: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=2000, ge=1, le=8000)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
    input_modalities: List[str] = Field(default_factory=lambda: ["text"])
    output_modalities: List[str] = Field(default_factory=lambda: ["text"])
    default_output_modalities: List[str] = Field(default_factory=lambda: ["text"])
    supported_response_formats: List[str] = Field(default_factory=lambda: ["text"])
    supports_vision: bool = False
    supports_audio_input: bool = False
    supports_audio_output: bool = False
    supports_video_input: bool = False
    supports_file_input: bool = False
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_reasoning: bool = False
    context_window: Optional[int] = Field(default=None, ge=1)
    max_output_tokens: Optional[int] = Field(default=None, ge=1)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    adapter_options: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_chat_text_output(self) -> "LLMModelConfig":
        output_modalities = _normalize_modalities(self.output_modalities, ["text"])
        if output_modalities != ["text"]:
            raise ValueError("LLM model output_modalities must remain ['text']")
        if self.task_type != "chat.completion":
            raise ValueError("LLM model task_type must be chat.completion")
        if self.endpoint_protocol and not supports_endpoint_protocol(self.endpoint_protocol):
            raise ValueError(f"Unsupported endpoint_protocol: {self.endpoint_protocol}")
        self.output_modalities = ["text"]
        self.default_output_modalities = ["text"]
        return self


class LLMModelCreate(BaseModel):
    """Create LLM model request"""
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., pattern=SUPPORTED_LLM_PROVIDER_PATTERN)
    model_id: str = Field(..., min_length=1, max_length=100)
    api_base: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = None
    config: Optional[LLMModelConfig] = Field(default_factory=LLMModelConfig)
    enabled: bool = Field(default=True)
    is_default: bool = Field(default=False)
    model_type: str = Field(default="llm", pattern="^(llm|embedding|rerank)$")


class LLMModelUpdate(BaseModel):
    """Update LLM model request"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    api_base: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = None
    config: Optional[LLMModelConfig] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    model_type: Optional[str] = Field(None, pattern="^(llm|embedding|rerank)$")


class LLMModelResponse(BaseModel):
    """LLM model response"""
    id: str
    name: str
    display_name: str
    provider: str
    model_id: str
    model_type: str
    api_base: Optional[str]
    has_api_key: bool
    config: Dict[str, Any]
    enabled: bool
    is_default: bool
    created_at: str
    updated_at: str


class LLMModelsListResponse(BaseModel):
    """List of LLM models"""
    models: List[LLMModelResponse]
    total: int


@router.get("/schema")
async def get_model_provider_schema():
    return {
        "adapters": adapter_schema(),
        "model_capability_catalog": model_capability_schema(),
    }


@router.get("", response_model=LLMModelsListResponse)
async def list_models(
    enabled_only: bool = True,
    tenant_id: str = Depends(get_current_tenant_id),
    db: DatabaseManager = Depends(get_db_manager)
):
    """
    Get list of available LLM models

    Args:
        enabled_only: Only return enabled models
        tenant_id: Current tenant ID
        db: Database manager

    Returns:
        List of LLM models
    """
    try:
        query = """
            SELECT
                id, name, display_name, provider, model_id, model_type,
                api_base, api_key_encrypted, config, enabled, is_default,
                created_at, updated_at
            FROM llm_models
            WHERE (tenant_id = $1 OR tenant_id IS NULL)
        """
        params = [tenant_id]

        if enabled_only:
            query += " AND enabled = true"

        query += " ORDER BY is_default DESC, display_name ASC"

        rows = await db.pool.fetch(query, *params)

        models = []
        for row in rows:
            models.append(LLMModelResponse(
                id=str(row['id']),
                name=row['name'],
                display_name=row['display_name'],
                provider=row['provider'],
                model_id=row['model_id'],
                model_type=row.get('model_type') or 'llm',
                api_base=row['api_base'],
                has_api_key=bool(row['api_key_encrypted']),
                config=_deserialize_config(row['config']),
                enabled=row['enabled'],
                is_default=row['is_default'],
                created_at=row['created_at'].isoformat(),
                updated_at=row['updated_at'].isoformat()
            ))

        return LLMModelsListResponse(models=models, total=len(models))

    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list models: {str(e)}"
        )


@router.get("/{model_id}", response_model=LLMModelResponse)
async def get_model(
    model_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: DatabaseManager = Depends(get_db_manager)
):
    """
    Get specific LLM model by ID

    Args:
        model_id: Model ID
        tenant_id: Current tenant ID
        db: Database manager

    Returns:
        LLM model details
    """
    try:
        query = """
            SELECT
                id, name, display_name, provider, model_id, model_type,
                api_base, api_key_encrypted, config, enabled, is_default,
                created_at, updated_at
            FROM llm_models
            WHERE id = $1 AND (tenant_id = $2 OR tenant_id IS NULL)
        """

        row = await db.pool.fetchrow(query, UUID(model_id), tenant_id)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found"
            )

        return LLMModelResponse(
            id=str(row['id']),
            name=row['name'],
            display_name=row['display_name'],
            provider=row['provider'],
            model_id=row['model_id'],
            model_type=row.get('model_type') or 'llm',
            api_base=row['api_base'],
            has_api_key=bool(row['api_key_encrypted']),
            config=_deserialize_config(row['config']),
            enabled=row['enabled'],
            is_default=row['is_default'],
            created_at=row['created_at'].isoformat(),
            updated_at=row['updated_at'].isoformat()
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model: {str(e)}"
        )


@router.post("", response_model=LLMModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    model: LLMModelCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    db: DatabaseManager = Depends(get_db_manager)
):
    """
    Create new LLM model configuration

    Args:
        model: Model creation data
        tenant_id: Current tenant ID
        user_id: Current user ID
        db: Database manager

    Returns:
        Created model details
    """
    try:
        # TODO: Encrypt API key before storing
        api_key_encrypted = model.api_key if model.api_key else None

        query = """
            INSERT INTO llm_models (
                name, display_name, provider, model_id, model_type,
                api_base, api_key_encrypted, config, enabled, is_default,
                tenant_id, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING
                id, name, display_name, provider, model_id, model_type,
                api_base, api_key_encrypted, config, enabled, is_default,
                created_at, updated_at
        """

        config_payload = _serialize_config(model.config.dict() if model.config else {})

        row = await db.pool.fetchrow(
            query,
            model.name,
            model.display_name,
            model.provider,
            model.model_id,
            model.model_type,
            model.api_base,
            api_key_encrypted,
            config_payload,
            model.enabled,
            model.is_default,
            tenant_id,
            UUID(user_id) if user_id else None
        )

        return LLMModelResponse(
            id=str(row['id']),
            name=row['name'],
            display_name=row['display_name'],
            provider=row['provider'],
            model_id=row['model_id'],
            model_type=row.get('model_type') or 'llm',
            api_base=row['api_base'],
            has_api_key=bool(row['api_key_encrypted']),
            config=_deserialize_config(row['config']),
            enabled=row['enabled'],
            is_default=row['is_default'],
            created_at=row['created_at'].isoformat(),
            updated_at=row['updated_at'].isoformat()
        )

    except Exception as e:
        logger.error(f"Failed to create model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create model: {str(e)}"
        )


@router.put("/{model_id}", response_model=LLMModelResponse)
async def update_model(
    model_id: str,
    model: LLMModelUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: DatabaseManager = Depends(get_db_manager)
):
    """
    Update LLM model configuration

    Args:
        model_id: Model ID
        model: Model update data
        tenant_id: Current tenant ID
        db: Database manager

    Returns:
        Updated model details
    """
    try:
        # Build dynamic update query
        updates = []
        params = []
        param_count = 1

        if model.display_name is not None:
            updates.append(f"display_name = ${param_count}")
            params.append(model.display_name)
            param_count += 1

        if model.api_base is not None:
            updates.append(f"api_base = ${param_count}")
            params.append(model.api_base)
            param_count += 1

        if model.api_key is not None:
            # TODO: Encrypt API key
            updates.append(f"api_key_encrypted = ${param_count}")
            params.append(model.api_key)
            param_count += 1

        if model.config is not None:
            updates.append(f"config = ${param_count}")
            params.append(_serialize_config(model.config.dict()))
            param_count += 1

        if model.enabled is not None:
            updates.append(f"enabled = ${param_count}")
            params.append(model.enabled)
            param_count += 1

        if model.is_default is not None:
            updates.append(f"is_default = ${param_count}")
            params.append(model.is_default)
            param_count += 1

        if model.model_type is not None:
            updates.append(f"model_type = ${param_count}")
            params.append(model.model_type)
            param_count += 1

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )

        updates.append(f"updated_at = NOW()")

        params.extend([UUID(model_id), tenant_id])

        query = f"""
            UPDATE llm_models
            SET {', '.join(updates)}
            WHERE id = ${param_count} AND (tenant_id = ${param_count + 1} OR tenant_id IS NULL)
            RETURNING
                id, name, display_name, provider, model_id, model_type,
                api_base, api_key_encrypted, config, enabled, is_default,
                created_at, updated_at
        """

        row = await db.pool.fetchrow(query, *params)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found"
            )

        return LLMModelResponse(
            id=str(row['id']),
            name=row['name'],
            display_name=row['display_name'],
            provider=row['provider'],
            model_id=row['model_id'],
            model_type=row.get('model_type') or 'llm',
            api_base=row['api_base'],
            has_api_key=bool(row['api_key_encrypted']),
            config=_deserialize_config(row['config']),
            enabled=row['enabled'],
            is_default=row['is_default'],
            created_at=row['created_at'].isoformat(),
            updated_at=row['updated_at'].isoformat()
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update model: {str(e)}"
        )


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: DatabaseManager = Depends(get_db_manager)
):
    """
    Delete LLM model configuration

    Args:
        model_id: Model ID
        tenant_id: Current tenant ID
        db: Database manager
    """
    try:
        query = """
            DELETE FROM llm_models
            WHERE id = $1 AND (tenant_id = $2 OR tenant_id IS NULL)
            RETURNING id
        """

        row = await db.pool.fetchrow(query, UUID(model_id), tenant_id)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found"
            )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete model: {str(e)}"
        )
