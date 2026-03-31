//go:build legacy_knowledge
// +build legacy_knowledge

package service

import (
	"errors"
	"sync"
	"time"

	"github.com/ai-platform/platform/models"
	"github.com/google/uuid"
)

var (
	ErrKnowledgeBaseNotFound = errors.New("知识库不存在")
	ErrDocumentNotFound      = errors.New("文档不存在")
)

// KnowledgeService handles knowledge base operations
type KnowledgeService struct {
	mu             sync.RWMutex
	knowledgeBases map[string]*models.KnowledgeBase
	documents      map[string][]*models.Document // key: knowledge_base_id
}

// NewKnowledgeService creates a new knowledge service
func NewKnowledgeService() *KnowledgeService {
	return &KnowledgeService{
		knowledgeBases: make(map[string]*models.KnowledgeBase),
		documents:      make(map[string][]*models.Document),
	}
}

// CreateKnowledgeBase creates a new knowledge base
func (s *KnowledgeService) CreateKnowledgeBase(req *models.CreateKnowledgeBaseRequest, userID, tenantID string) (*models.KnowledgeBase, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	kb := &models.KnowledgeBase{
		ID:            uuid.New().String(),
		Name:          req.Name,
		Description:   req.Description,
		Type:          req.Type,
		IsPublic:      req.IsPublic,
		TenantID:      tenantID,
		UserID:        userID,
		DocumentCount: 0,
		CreatedAt:     time.Now(),
		UpdatedAt:     time.Now(),
	}

	if kb.Type == "" {
		kb.Type = "general"
	}

	s.knowledgeBases[kb.ID] = kb
	s.documents[kb.ID] = []*models.Document{}

	return kb, nil
}

// GetKnowledgeBase retrieves a knowledge base by ID
func (s *KnowledgeService) GetKnowledgeBase(id, userID, tenantID string) (*models.KnowledgeBase, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	kb, exists := s.knowledgeBases[id]
	if !exists {
		return nil, ErrKnowledgeBaseNotFound
	}

	// Check access permissions
	if !kb.IsPublic && kb.TenantID != tenantID {
		return nil, ErrUnauthorized
	}

	return kb, nil
}

// ListKnowledgeBases lists all knowledge bases for a tenant
func (s *KnowledgeService) ListKnowledgeBases(tenantID string) ([]*models.KnowledgeBase, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var result []*models.KnowledgeBase
	for _, kb := range s.knowledgeBases {
		if kb.TenantID == tenantID || kb.IsPublic {
			result = append(result, kb)
		}
	}

	return result, nil
}

// UpdateKnowledgeBase updates a knowledge base
func (s *KnowledgeService) UpdateKnowledgeBase(id string, req *models.UpdateKnowledgeBaseRequest, userID, tenantID string) (*models.KnowledgeBase, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	kb, exists := s.knowledgeBases[id]
	if !exists {
		return nil, ErrKnowledgeBaseNotFound
	}

	// Check ownership
	if kb.TenantID != tenantID {
		return nil, ErrUnauthorized
	}

	kb.Name = req.Name
	kb.Description = req.Description
	kb.Type = req.Type
	kb.IsPublic = req.IsPublic
	kb.UpdatedAt = time.Now()

	return kb, nil
}

// DeleteKnowledgeBase deletes a knowledge base
func (s *KnowledgeService) DeleteKnowledgeBase(id, userID, tenantID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	kb, exists := s.knowledgeBases[id]
	if !exists {
		return ErrKnowledgeBaseNotFound
	}

	// Check ownership
	if kb.TenantID != tenantID {
		return ErrUnauthorized
	}

	delete(s.knowledgeBases, id)
	delete(s.documents, id)

	return nil
}

// AddDocument adds a document to a knowledge base
func (s *KnowledgeService) AddDocument(kbID, name, content string, size int64, userID, tenantID string) (*models.Document, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	kb, exists := s.knowledgeBases[kbID]
	if !exists {
		return nil, ErrKnowledgeBaseNotFound
	}

	// Check ownership
	if kb.TenantID != tenantID {
		return nil, ErrUnauthorized
	}

	doc := &models.Document{
		ID:              uuid.New().String(),
		KnowledgeBaseID: kbID,
		Name:            name,
		Content:         content,
		Size:            size,
		Type:            getFileExtension(name),
		Status:          "available",
		UploadedAt:      time.Now(),
		UpdatedAt:       time.Now(),
	}

	s.documents[kbID] = append(s.documents[kbID], doc)
	kb.DocumentCount++
	kb.UpdatedAt = time.Now()

	return doc, nil
}

// GetDocuments retrieves all documents in a knowledge base
func (s *KnowledgeService) GetDocuments(kbID, userID, tenantID string) ([]*models.Document, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	kb, exists := s.knowledgeBases[kbID]
	if !exists {
		return nil, ErrKnowledgeBaseNotFound
	}

	// Check access permissions
	if !kb.IsPublic && kb.TenantID != tenantID {
		return nil, ErrUnauthorized
	}

	docs := s.documents[kbID]
	if docs == nil {
		return []*models.Document{}, nil
	}

	return docs, nil
}

// DeleteDocument deletes a document from a knowledge base
func (s *KnowledgeService) DeleteDocument(kbID, docID, userID, tenantID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	kb, exists := s.knowledgeBases[kbID]
	if !exists {
		return ErrKnowledgeBaseNotFound
	}

	// Check ownership
	if kb.TenantID != tenantID {
		return ErrUnauthorized
	}

	docs := s.documents[kbID]
	for i, doc := range docs {
		if doc.ID == docID {
			s.documents[kbID] = append(docs[:i], docs[i+1:]...)
			kb.DocumentCount--
			kb.UpdatedAt = time.Now()
			return nil
		}
	}

	return ErrDocumentNotFound
}

// getFileExtension extracts file extension from filename
func getFileExtension(filename string) string {
	for i := len(filename) - 1; i >= 0; i-- {
		if filename[i] == '.' {
			return filename[i+1:]
		}
	}
	return ""
}
