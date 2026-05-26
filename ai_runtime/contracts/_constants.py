from __future__ import annotations

TEXT_CANDIDATE_KEYS = (
    "final_output_text",
    "answer",
    "summary",
    "final_answer",
    "response",
    "message",
    "content",
    "result",
)
PLAN_KEYS = ("task_plan", "plan", "implementation_plan")
CITATION_KEYS = ("citations", "sources", "references")
FINDING_KEYS = ("review_findings", "findings", "issues", "risks")
CODE_FILE_KEYS = ("code_files", "files")
TABLE_KEYS = ("table", "tables", "rows")
EXCERPT_KEYS = ("document_excerpt", "document_excerpts", "excerpts", "excerpt")
PAGED_KEYS = ("paged_collection", "paged_results", "page", "page_result")
MEDIA_KEYS = ("media_gallery", "image_gallery", "images", "media")
FILE_BUNDLE_KEYS = ("file_bundle", "attachments", "resources", "downloads")
DIRECTORY_TREE_KEYS = ("directory_tree", "tree", "file_tree")
DOCUMENT_PAGE_KEYS = ("document_pages", "pages", "document_preview_pages")
ARCHIVE_BUNDLE_KEYS = ("archive_bundle", "archive_entries", "compressed_bundle")
ARTIFACT_TYPE_PRIORITY = {
    "answer": 0,
    "workspace_summary": 1,
    "review_findings": 1,
    "citations": 2,
    "code_files": 3,
    "code_patch": 4,
    "verification_report": 5,
    "task_plan": 6,
    "table": 7,
    "paged_collection": 8,
    "directory_tree": 9,
    "document_pages": 10,
    "document_excerpt": 11,
    "media_gallery": 12,
    "archive_bundle": 13,
    "file_bundle": 14,
}
IMPLICIT_LIST_KEYS = ("items", "results", "entries", "records", "matches", "documents", "data")
CODE_FILE_EXTENSIONS = {
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cs": "csharp", ".css": "css",
    ".go": "go", ".h": "c", ".html": "html", ".java": "java", ".js": "javascript",
    ".json": "json", ".jsx": "javascript", ".kt": "kotlin", ".md": "markdown",
    ".php": "php", ".py": "python", ".rb": "ruby", ".rs": "rust", ".sh": "bash",
    ".sql": "sql", ".swift": "swift", ".ts": "typescript", ".tsx": "typescript",
    ".txt": "text", ".xml": "xml", ".yaml": "yaml", ".yml": "yaml", ".zsh": "zsh",
}
MEDIA_EXTENSIONS = {
    ".apng": "image", ".avif": "image", ".gif": "image", ".jpeg": "image",
    ".jpg": "image", ".png": "image", ".svg": "image", ".webp": "image",
    ".bmp": "image", ".ico": "image",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".m4a": "audio", ".aac": "audio",
    ".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video",
}
