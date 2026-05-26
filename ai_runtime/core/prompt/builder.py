from typing import Any, Dict, List, Optional, Sequence
from pathlib import Path
import json

from ai_runtime.core.llm.messages import ContentPart, UnifiedMessage, build_text_part, normalize_messages


class PromptTemplate:
    """Prompt template class"""

    def __init__(self, template: str, variables: Optional[List[str]] = None):
        self.template = template
        self.variables = variables or []

    def format(self, **kwargs) -> str:
        """Format template with variables"""
        return self.template.format(**kwargs)


class PromptBuilder:
    """Prompt builder for constructing AI prompts"""

    def __init__(self, templates_dir: Optional[str] = None):
        self.templates_dir = Path(templates_dir) if templates_dir else Path(__file__).parent / "templates"
        self.templates: Dict[str, PromptTemplate] = {}
        self._load_templates()

    def _load_templates(self):
        """Load templates from directory"""
        if not self.templates_dir.exists():
            return

        for template_file in self.templates_dir.glob("*.json"):
            with open(template_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                name = template_file.stem
                self.templates[name] = PromptTemplate(
                    template=data.get('template', ''),
                    variables=data.get('variables', [])
                )

    def build(self,
              system_prompt: Optional[str] = None,
              user_message: Optional[str] = None,
              context: Optional[str] = None,
              history: Optional[List[Dict]] = None,
              template_name: Optional[str] = None,
              **kwargs) -> List[Dict[str, str]]:
        """
        Build messages for LLM

        Args:
            system_prompt: System prompt
            user_message: User message
            context: Additional context (e.g., RAG results)
            history: Chat history
            template_name: Name of template to use
            **kwargs: Template variables

        Returns:
            List of message dicts
        """
        messages = []

        # System message
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # History
        if history:
            messages.extend(history)

        # User message with context
        if user_message:
            content = user_message

            # Add context from RAG if provided
            if context:
                content = f"Context:\n{context}\n\nQuestion: {user_message}"

            # Use template if provided
            if template_name and template_name in self.templates:
                template = self.templates[template_name]
                content = template.format(
                    message=user_message,
                    context=context or "",
                    **kwargs
                )

            messages.append({"role": "user", "content": content})

        return messages

    def build_unified(
        self,
        system_prompt: Optional[str] = None,
        user_message: Optional[str] = None,
        context: Optional[str] = None,
        history: Optional[Sequence[UnifiedMessage | Dict[str, Any]]] = None,
        template_name: Optional[str] = None,
        user_parts: Optional[Sequence[ContentPart | Dict[str, Any]]] = None,
        **kwargs,
    ) -> list[UnifiedMessage]:
        messages: list[UnifiedMessage] = []

        if system_prompt:
            messages.append(
                UnifiedMessage(
                    role="system",
                    content=[build_text_part(system_prompt)],
                )
            )

        if history:
            messages.extend(normalize_messages(history))

        if user_message or user_parts:
            content_parts = list(normalize_messages([{"role": "user", "content": user_parts or []}])[0].content if user_parts else [])
            if user_message:
                has_text = any(part.type == "text" and (part.text or "").strip() for part in content_parts)
                if not has_text:
                    content_parts.insert(0, build_text_part(user_message))

            if context:
                content_parts.insert(
                    0,
                    build_text_part(f"Context:\n{context}\n\nQuestion: {user_message or ''}"),
                )

            if template_name and template_name in self.templates:
                template = self.templates[template_name]
                content_parts = [build_text_part(template.format(message=user_message or "", context=context or "", **kwargs))]

            messages.append(
                UnifiedMessage(
                    role="user",
                    content=content_parts or [build_text_part(user_message or "")],
                )
            )

        return messages

    def add_template(self, name: str, template: str, variables: Optional[List[str]] = None):
        """Add a custom template"""
        self.templates[name] = PromptTemplate(template, variables)

    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """Get template by name"""
        return self.templates.get(name)
