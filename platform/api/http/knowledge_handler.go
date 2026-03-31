//go:build legacy_knowledge
// +build legacy_knowledge

package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/models"
	"github.com/ai-platform/platform/service"
)

// KnowledgeHandler handles knowledge base HTTP requests
type KnowledgeHandler struct {
	knowledgeService *service.KnowledgeService
}

// NewKnowledgeHandler creates a new knowledge handler
func NewKnowledgeHandler(knowledgeService *service.KnowledgeService) *KnowledgeHandler {
	return &KnowledgeHandler{
		knowledgeService: knowledgeService,
	}
}

// HandleListKnowledgeBases handles GET /api/v1/knowledge
func (h *KnowledgeHandler) HandleListKnowledgeBases(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// List knowledge bases
	kbs, err := h.knowledgeService.ListKnowledgeBases(user.TenantID)
	if err != nil {
		respondError(w, "获取知识库列表失败", http.StatusInternalServerError)
		return
	}

	respondJSON(w, kbs, http.StatusOK)
}

// HandleGetKnowledgeBase handles GET /api/v1/knowledge/{id}
func (h *KnowledgeHandler) HandleGetKnowledgeBase(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Extract ID from path
	id := extractIDFromPath(r.URL.Path, "/api/v1/knowledge/")
	if id == "" {
		respondError(w, "无效的知识库ID", http.StatusBadRequest)
		return
	}

	// Get knowledge base
	kb, err := h.knowledgeService.GetKnowledgeBase(id, user.ID, user.TenantID)
	if err != nil {
		if err == service.ErrKnowledgeBaseNotFound {
			respondError(w, "知识库不存在", http.StatusNotFound)
		} else if err == service.ErrUnauthorized {
			respondError(w, "无权访问此知识库", http.StatusForbidden)
		} else {
			respondError(w, "获取知识库失败", http.StatusInternalServerError)
		}
		return
	}

	respondJSON(w, kb, http.StatusOK)
}

// HandleCreateKnowledgeBase handles POST /api/v1/knowledge
func (h *KnowledgeHandler) HandleCreateKnowledgeBase(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Parse request
	var req models.CreateKnowledgeBaseRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "请求数据格式错误", http.StatusBadRequest)
		return
	}

	// Validate request
	if req.Name == "" {
		respondError(w, "知识库名称不能为空", http.StatusBadRequest)
		return
	}

	// Create knowledge base
	kb, err := h.knowledgeService.CreateKnowledgeBase(&req, user.ID, user.TenantID)
	if err != nil {
		respondError(w, "创建知识库失败", http.StatusInternalServerError)
		return
	}

	respondJSON(w, kb, http.StatusCreated)
}

// HandleUpdateKnowledgeBase handles PUT /api/v1/knowledge/{id}
func (h *KnowledgeHandler) HandleUpdateKnowledgeBase(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Extract ID from path
	id := extractIDFromPath(r.URL.Path, "/api/v1/knowledge/")
	if id == "" {
		respondError(w, "无效的知识库ID", http.StatusBadRequest)
		return
	}

	// Parse request
	var req models.UpdateKnowledgeBaseRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "请求数据格式错误", http.StatusBadRequest)
		return
	}

	// Validate request
	if req.Name == "" {
		respondError(w, "知识库名称不能为空", http.StatusBadRequest)
		return
	}

	// Update knowledge base
	kb, err := h.knowledgeService.UpdateKnowledgeBase(id, &req, user.ID, user.TenantID)
	if err != nil {
		if err == service.ErrKnowledgeBaseNotFound {
			respondError(w, "知识库不存在", http.StatusNotFound)
		} else if err == service.ErrUnauthorized {
			respondError(w, "无权修改此知识库", http.StatusForbidden)
		} else {
			respondError(w, "更新知识库失败", http.StatusInternalServerError)
		}
		return
	}

	respondJSON(w, kb, http.StatusOK)
}

// HandleDeleteKnowledgeBase handles DELETE /api/v1/knowledge/{id}
func (h *KnowledgeHandler) HandleDeleteKnowledgeBase(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Extract ID from path
	id := extractIDFromPath(r.URL.Path, "/api/v1/knowledge/")
	if id == "" {
		respondError(w, "无效的知识库ID", http.StatusBadRequest)
		return
	}

	// Delete knowledge base
	err := h.knowledgeService.DeleteKnowledgeBase(id, user.ID, user.TenantID)
	if err != nil {
		if err == service.ErrKnowledgeBaseNotFound {
			respondError(w, "知识库不存在", http.StatusNotFound)
		} else if err == service.ErrUnauthorized {
			respondError(w, "无权删除此知识库", http.StatusForbidden)
		} else {
			respondError(w, "删除知识库失败", http.StatusInternalServerError)
		}
		return
	}

	respondJSON(w, map[string]string{"message": "删除成功"}, http.StatusOK)
}

// HandleUploadDocument handles POST /api/v1/knowledge/{id}/documents
func (h *KnowledgeHandler) HandleUploadDocument(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Extract knowledge base ID from path
	kbID := extractIDFromPath(r.URL.Path, "/api/v1/knowledge/")
	if kbID == "" {
		respondError(w, "无效的知识库ID", http.StatusBadRequest)
		return
	}

	// Parse multipart form
	err := r.ParseMultipartForm(20 << 20) // 20 MB max
	if err != nil {
		respondError(w, "解析文件失败", http.StatusBadRequest)
		return
	}

	// Get file from form
	file, header, err := r.FormFile("file")
	if err != nil {
		respondError(w, "未找到上传文件", http.StatusBadRequest)
		return
	}
	defer file.Close()

	// Read file content
	content, err := io.ReadAll(file)
	if err != nil {
		respondError(w, "读取文件失败", http.StatusInternalServerError)
		return
	}

	// Add document
	doc, err := h.knowledgeService.AddDocument(
		kbID,
		header.Filename,
		string(content),
		header.Size,
		user.ID,
		user.TenantID,
	)
	if err != nil {
		if err == service.ErrKnowledgeBaseNotFound {
			respondError(w, "知识库不存在", http.StatusNotFound)
		} else if err == service.ErrUnauthorized {
			respondError(w, "无权上传文档到此知识库", http.StatusForbidden)
		} else {
			respondError(w, "上传文档失败", http.StatusInternalServerError)
		}
		return
	}

	respondJSON(w, doc, http.StatusCreated)
}

// HandleGetDocuments handles GET /api/v1/knowledge/{id}/documents
func (h *KnowledgeHandler) HandleGetDocuments(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Extract knowledge base ID from path
	kbID := extractIDFromPath(r.URL.Path, "/api/v1/knowledge/")
	if kbID == "" {
		respondError(w, "无效的知识库ID", http.StatusBadRequest)
		return
	}

	// Get documents
	docs, err := h.knowledgeService.GetDocuments(kbID, user.ID, user.TenantID)
	if err != nil {
		if err == service.ErrKnowledgeBaseNotFound {
			respondError(w, "知识库不存在", http.StatusNotFound)
		} else if err == service.ErrUnauthorized {
			respondError(w, "无权访问此知识库", http.StatusForbidden)
		} else {
			respondError(w, "获取文档列表失败", http.StatusInternalServerError)
		}
		return
	}

	respondJSON(w, docs, http.StatusOK)
}

// HandleDeleteDocument handles DELETE /api/v1/knowledge/{kbID}/documents/{docID}
func (h *KnowledgeHandler) HandleDeleteDocument(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Extract IDs from path
	path := r.URL.Path
	parts := strings.Split(strings.TrimPrefix(path, "/api/v1/knowledge/"), "/")
	if len(parts) < 3 {
		respondError(w, "无效的请求路径", http.StatusBadRequest)
		return
	}

	kbID := parts[0]
	docID := parts[2]

	// Delete document
	err := h.knowledgeService.DeleteDocument(kbID, docID, user.ID, user.TenantID)
	if err != nil {
		if err == service.ErrKnowledgeBaseNotFound {
			respondError(w, "知识库不存在", http.StatusNotFound)
		} else if err == service.ErrDocumentNotFound {
			respondError(w, "文档不存在", http.StatusNotFound)
		} else if err == service.ErrUnauthorized {
			respondError(w, "无权删除此文档", http.StatusForbidden)
		} else {
			respondError(w, "删除文档失败", http.StatusInternalServerError)
		}
		return
	}

	respondJSON(w, map[string]string{"message": "删除成功"}, http.StatusOK)
}

// extractIDFromPath extracts ID from URL path
func extractIDFromPath(path, prefix string) string {
	if !strings.HasPrefix(path, prefix) {
		return ""
	}

	remaining := strings.TrimPrefix(path, prefix)
	parts := strings.Split(remaining, "/")
	if len(parts) > 0 && parts[0] != "" {
		return parts[0]
	}

	return ""
}
