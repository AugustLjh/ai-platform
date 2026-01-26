package models

import "time"

// KnowledgeBase represents a knowledge base
type KnowledgeBase struct {
	ID            string    `json:"id"`
	Name          string    `json:"name"`
	Description   string    `json:"description"`
	Type          string    `json:"type"` // general, technical, business, personal
	IsPublic      bool      `json:"is_public"`
	TenantID      string    `json:"tenant_id"`
	UserID        string    `json:"user_id"`
	DocumentCount int       `json:"document_count"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// Document represents a document in a knowledge base
type Document struct {
	ID              string    `json:"id"`
	KnowledgeBaseID string    `json:"knowledge_base_id"`
	Name            string    `json:"name"`
	Content         string    `json:"content,omitempty"`
	Size            int64     `json:"size"`
	Type            string    `json:"type"` // file extension
	UploadedAt      time.Time `json:"uploaded_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

// CreateKnowledgeBaseRequest represents a request to create a knowledge base
type CreateKnowledgeBaseRequest struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Type        string `json:"type"`
	IsPublic    bool   `json:"is_public"`
}

// UpdateKnowledgeBaseRequest represents a request to update a knowledge base
type UpdateKnowledgeBaseRequest struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Type        string `json:"type"`
	IsPublic    bool   `json:"is_public"`
}