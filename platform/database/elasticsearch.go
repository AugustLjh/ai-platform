package database

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/elastic/go-elasticsearch/v8"
	"github.com/elastic/go-elasticsearch/v8/esapi"
)

// ElasticsearchConfig holds Elasticsearch configuration
type ElasticsearchConfig struct {
	Addresses []string
	Username  string
	Password  string
}

// NewElasticsearchClient creates a new Elasticsearch client
func NewElasticsearchClient(config *ElasticsearchConfig) (*elasticsearch.Client, error) {
	cfg := elasticsearch.Config{
		Addresses: config.Addresses,
		Username:  config.Username,
		Password:  config.Password,
	}

	client, err := elasticsearch.NewClient(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to create elasticsearch client: %w", err)
	}

	// Ping to verify connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	res, err := client.Ping(client.Ping.WithContext(ctx))
	if err != nil {
		return nil, fmt.Errorf("failed to ping elasticsearch: %w", err)
	}
	defer res.Body.Close()

	if res.IsError() {
		return nil, fmt.Errorf("elasticsearch ping failed: %s", res.String())
	}

	return client, nil
}

// VectorDocument represents a document with vector embeddings
type VectorDocument struct {
	ID        string                 `json:"id"`
	TenantID  string                 `json:"tenant_id"`
	Title     string                 `json:"title"`
	Content   string                 `json:"content"`
	Embedding []float32              `json:"embedding"`
	Metadata  map[string]interface{} `json:"metadata"`
	CreatedAt time.Time              `json:"created_at"`
}

// SearchResult represents a search result
type SearchResult struct {
	ID       string
	Score    float64
	Document VectorDocument
}

// ElasticsearchVectorStore implements vector store with Elasticsearch
type ElasticsearchVectorStore struct {
	client    *elasticsearch.Client
	indexName string
}

// NewElasticsearchVectorStore creates a new Elasticsearch vector store
func NewElasticsearchVectorStore(client *elasticsearch.Client, indexName string) *ElasticsearchVectorStore {
	return &ElasticsearchVectorStore{
		client:    client,
		indexName: indexName,
	}
}

// CreateIndex creates the index with vector mapping
func (s *ElasticsearchVectorStore) CreateIndex(ctx context.Context, dimensions int) error {
	// Index mapping with dense_vector for embeddings
	mapping := map[string]interface{}{
		"mappings": map[string]interface{}{
			"properties": map[string]interface{}{
				"id":         map[string]string{"type": "keyword"},
				"tenant_id":  map[string]string{"type": "keyword"},
				"title":      map[string]string{"type": "text"},
				"content":    map[string]string{"type": "text"},
				"created_at": map[string]string{"type": "date"},
				"embedding": map[string]interface{}{
					"type":       "dense_vector",
					"dims":       dimensions,
					"index":      true,
					"similarity": "cosine",
				},
				"metadata": map[string]string{"type": "object"},
			},
		},
	}

	body, err := json.Marshal(mapping)
	if err != nil {
		return fmt.Errorf("failed to marshal mapping: %w", err)
	}

	req := esapi.IndicesCreateRequest{
		Index: s.indexName,
		Body:  bytes.NewReader(body),
	}

	res, err := req.Do(ctx, s.client)
	if err != nil {
		return fmt.Errorf("failed to create index: %w", err)
	}
	defer res.Body.Close()

	if res.IsError() {
		body, _ := io.ReadAll(res.Body)
		// Ignore "already exists" error
		if !strings.Contains(string(body), "resource_already_exists_exception") {
			return fmt.Errorf("failed to create index: %s", string(body))
		}
	}

	return nil
}

// IndexDocument indexes a document with vector embedding
func (s *ElasticsearchVectorStore) IndexDocument(ctx context.Context, doc *VectorDocument) error {
	body, err := json.Marshal(doc)
	if err != nil {
		return fmt.Errorf("failed to marshal document: %w", err)
	}

	req := esapi.IndexRequest{
		Index:      s.indexName,
		DocumentID: doc.ID,
		Body:       bytes.NewReader(body),
		Refresh:    "true",
	}

	res, err := req.Do(ctx, s.client)
	if err != nil {
		return fmt.Errorf("failed to index document: %w", err)
	}
	defer res.Body.Close()

	if res.IsError() {
		body, _ := io.ReadAll(res.Body)
		return fmt.Errorf("failed to index document: %s", string(body))
	}

	return nil
}

// SearchByVector searches documents by vector similarity
func (s *ElasticsearchVectorStore) SearchByVector(ctx context.Context, vector []float32, tenantID string, topK int) ([]*SearchResult, error) {
	query := map[string]interface{}{
		"knn": map[string]interface{}{
			"field":          "embedding",
			"query_vector":   vector,
			"k":              topK,
			"num_candidates": topK * 10,
			"filter": map[string]interface{}{
				"term": map[string]string{
					"tenant_id": tenantID,
				},
			},
		},
		"_source": []string{"id", "tenant_id", "title", "content", "metadata", "created_at"},
	}

	body, err := json.Marshal(query)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal query: %w", err)
	}

	req := esapi.SearchRequest{
		Index: []string{s.indexName},
		Body:  bytes.NewReader(body),
	}

	res, err := req.Do(ctx, s.client)
	if err != nil {
		return nil, fmt.Errorf("failed to search: %w", err)
	}
	defer res.Body.Close()

	if res.IsError() {
		body, _ := io.ReadAll(res.Body)
		return nil, fmt.Errorf("search failed: %s", string(body))
	}

	var result map[string]interface{}
	if err := json.NewDecoder(res.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	hits, ok := result["hits"].(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid response format")
	}

	hitsList, ok := hits["hits"].([]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid hits format")
	}

	var results []*SearchResult
	for _, hit := range hitsList {
		hitMap, ok := hit.(map[string]interface{})
		if !ok {
			continue
		}

		score, _ := hitMap["_score"].(float64)
		source, _ := hitMap["_source"].(map[string]interface{})

		doc := VectorDocument{
			ID:       getString(source, "id"),
			TenantID: getString(source, "tenant_id"),
			Title:    getString(source, "title"),
			Content:  getString(source, "content"),
			Metadata: getMap(source, "metadata"),
		}

		results = append(results, &SearchResult{
			ID:       doc.ID,
			Score:    score,
			Document: doc,
		})
	}

	return results, nil
}

// SearchByText searches documents by text (full-text search)
func (s *ElasticsearchVectorStore) SearchByText(ctx context.Context, text, tenantID string, topK int) ([]*SearchResult, error) {
	query := map[string]interface{}{
		"query": map[string]interface{}{
			"bool": map[string]interface{}{
				"must": []map[string]interface{}{
					{
						"multi_match": map[string]interface{}{
							"query":  text,
							"fields": []string{"title^2", "content"},
						},
					},
					{
						"term": map[string]string{
							"tenant_id": tenantID,
						},
					},
				},
			},
		},
		"size":    topK,
		"_source": []string{"id", "tenant_id", "title", "content", "metadata", "created_at"},
	}

	body, err := json.Marshal(query)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal query: %w", err)
	}

	req := esapi.SearchRequest{
		Index: []string{s.indexName},
		Body:  bytes.NewReader(body),
	}

	res, err := req.Do(ctx, s.client)
	if err != nil {
		return nil, fmt.Errorf("failed to search: %w", err)
	}
	defer res.Body.Close()

	if res.IsError() {
		body, _ := io.ReadAll(res.Body)
		return nil, fmt.Errorf("search failed: %s", string(body))
	}

	var result map[string]interface{}
	if err := json.NewDecoder(res.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	hits, ok := result["hits"].(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid response format")
	}

	hitsList, ok := hits["hits"].([]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid hits format")
	}

	var results []*SearchResult
	for _, hit := range hitsList {
		hitMap, ok := hit.(map[string]interface{})
		if !ok {
			continue
		}

		score, _ := hitMap["_score"].(float64)
		source, _ := hitMap["_source"].(map[string]interface{})

		doc := VectorDocument{
			ID:       getString(source, "id"),
			TenantID: getString(source, "tenant_id"),
			Title:    getString(source, "title"),
			Content:  getString(source, "content"),
			Metadata: getMap(source, "metadata"),
		}

		results = append(results, &SearchResult{
			ID:       doc.ID,
			Score:    score,
			Document: doc,
		})
	}

	return results, nil
}

// DeleteDocument deletes a document
func (s *ElasticsearchVectorStore) DeleteDocument(ctx context.Context, docID string) error {
	req := esapi.DeleteRequest{
		Index:      s.indexName,
		DocumentID: docID,
		Refresh:    "true",
	}

	res, err := req.Do(ctx, s.client)
	if err != nil {
		return fmt.Errorf("failed to delete document: %w", err)
	}
	defer res.Body.Close()

	if res.IsError() {
		body, _ := io.ReadAll(res.Body)
		return fmt.Errorf("failed to delete document: %s", string(body))
	}

	return nil
}

// Helper functions
func getString(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func getMap(m map[string]interface{}, key string) map[string]interface{} {
	if v, ok := m[key].(map[string]interface{}); ok {
		return v
	}
	return nil
}
