package grpc

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"

	"github.com/ai-platform/platform/database"
	pb "github.com/ai-platform/platform/proto/chat"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// ChatMessage represents a chat message
type ChatMessage struct {
	SessionID string
	MessageID string
	Type      int32
	Content   string
	Error     string
	Metadata  map[string]string
}

// ChatRequest represents a chat request
type ChatRequest struct {
	SessionID string
	UserID    string
	TenantID  string
	Message   string
	Metadata  map[string]string
	Config    *ChatConfig
}

// ChatConfig holds chat configuration
type ChatConfig struct {
	Model           string
	Temperature     float32
	MaxTokens       int32
	UseRAG          bool
	Tools           []string
	KnowledgeBaseID string
}

// AIClient handles communication with the AI Runtime (HTTP streaming preferred).
type AIClient struct {
	conn        *grpc.ClientConn
	client      pb.ChatServiceClient
	address     string
	httpBaseURL string
	httpClient  *http.Client
}

// NewAIClient creates a new AI client
func NewAIClient(address, httpBaseURL string) (*AIClient, error) {
	httpBaseURL = strings.TrimRight(httpBaseURL, "/")
	if httpBaseURL != "" {
		return &AIClient{
			address:     address,
			httpBaseURL: httpBaseURL,
			httpClient:  &http.Client{},
		}, nil
	}

	if address == "" {
		return nil, errors.New("AI runtime address is empty")
	}

	conn, err := grpc.DialContext(
		context.Background(),
		address,
		grpc.WithTransportCredentials(insecure.NewCredentials()), // TODO: Use TLS in production
	)
	if err != nil {
		return nil, err
	}

	client := pb.NewChatServiceClient(conn)

	return &AIClient{
		conn:    conn,
		client:  client,
		address: address,
	}, nil
}

// Close closes the gRPC connection
func (c *AIClient) Close() error {
	if c.conn == nil {
		return nil
	}
	return c.conn.Close()
}

// StreamChat streams chat with AI runtime using HTTP SSE when available.
func (c *AIClient) StreamChat(ctx context.Context, req *ChatRequest) (<-chan *ChatMessage, error) {
	if c.httpBaseURL != "" {
		return c.streamChatHTTP(ctx, req)
	}

	// Convert request to protobuf
	pbReq := &pb.ChatRequest{
		SessionId: req.SessionID,
		UserId:    req.UserID,
		TenantId:  req.TenantID,
		Message:   req.Message,
		Metadata:  req.Metadata,
		Config: &pb.ChatConfig{
			Model:       req.Config.Model,
			Temperature: req.Config.Temperature,
			MaxTokens:   req.Config.MaxTokens,
			UseRag:      req.Config.UseRAG,
			Tools:       req.Config.Tools,
		},
	}

	// Call gRPC streaming method
	stream, err := c.client.StreamChat(ctx, pbReq)
	if err != nil {
		return nil, err
	}

	// Create output channel
	messageChan := make(chan *ChatMessage, 100)

	// Start goroutine to receive stream
	go func() {
		defer close(messageChan)

		for {
			select {
			case <-ctx.Done():
				messageChan <- &ChatMessage{
					Type:  5, // ERROR
					Error: "Request cancelled",
				}
				return
			default:
				resp, err := stream.Recv()
				if err == io.EOF {
					// Stream ended normally
					return
				}
				if err != nil {
					// Stream error
					log.Printf("[AIClient] Stream error: %v", err)
					messageChan <- &ChatMessage{
						Type:  5, // ERROR
						Error: err.Error(),
					}
					return
				}

				// Convert protobuf response to internal message
				messageChan <- &ChatMessage{
					SessionID: resp.SessionId,
					MessageID: resp.MessageId,
					Type:      int32(resp.Type),
					Content:   resp.Content,
					Error:     resp.Error,
					Metadata:  resp.Metadata,
				}
			}
		}
	}()

	return messageChan, nil
}

type httpChatRequest struct {
	SessionID string            `json:"session_id"`
	UserID    string            `json:"user_id"`
	TenantID  string            `json:"tenant_id"`
	Message   string            `json:"message"`
	Metadata  map[string]string `json:"metadata"`
	Config    httpChatConfig    `json:"config"`
}

type httpChatConfig struct {
	Model           string  `json:"model"`
	UseRAG          bool    `json:"use_rag"`
	Temperature     float32 `json:"temperature"`
	MaxTokens       int32   `json:"max_tokens"`
	KnowledgeBaseID string  `json:"knowledge_base_id"`
}

type httpChatChunk struct {
	SessionID string            `json:"session_id"`
	MessageID string            `json:"message_id"`
	Type      int32             `json:"type"`
	Content   string            `json:"content"`
	Error     string            `json:"error"`
	Metadata  map[string]string `json:"metadata"`
}

type AgentRunCreateRequest struct {
	AgentDefinitionID string          `json:"agent_definition_id"`
	Input             json.RawMessage `json:"input"`
	TenantID          string          `json:"tenant_id"`
	UserID            string          `json:"user_id,omitempty"`
	SessionID         string          `json:"session_id,omitempty"`
	Metadata          map[string]any  `json:"metadata,omitempty"`
	AutoStart         bool            `json:"auto_start"`
}

type runtimeAgentRunSummaryResponse struct {
	Run database.AgentRun `json:"run"`
}

type runtimeAgentResumeRequest struct {
	InputPatch json.RawMessage `json:"input_patch"`
}

func (c *AIClient) streamChatHTTP(ctx context.Context, req *ChatRequest) (<-chan *ChatMessage, error) {
	if c.httpClient == nil {
		c.httpClient = &http.Client{}
	}

	config := req.Config
	if config == nil {
		config = &ChatConfig{
			Temperature: 0.7,
			MaxTokens:   2000,
		}
	}

	payload := httpChatRequest{
		SessionID: req.SessionID,
		UserID:    req.UserID,
		TenantID:  req.TenantID,
		Message:   req.Message,
		Metadata:  req.Metadata,
		Config: httpChatConfig{
			Model:           config.Model,
			UseRAG:          config.UseRAG,
			Temperature:     config.Temperature,
			MaxTokens:       config.MaxTokens,
			KnowledgeBaseID: config.KnowledgeBaseID,
		},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	url := c.httpBaseURL + "/api/v1/chat/stream"
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, err
	}

	messageChan := make(chan *ChatMessage, 100)

	go func() {
		defer close(messageChan)
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
			messageChan <- &ChatMessage{
				Type:  5,
				Error: strings.TrimSpace(string(respBody)),
			}
			return
		}

		reader := bufio.NewReader(resp.Body)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				if errors.Is(err, io.EOF) {
					return
				}
				if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
					messageChan <- &ChatMessage{
						Type:  5,
						Error: "Request cancelled",
					}
					return
				}
				messageChan <- &ChatMessage{
					Type:  5,
					Error: err.Error(),
				}
				return
			}

			line = strings.TrimRight(line, "\r\n")
			if line == "" {
				continue
			}
			if !strings.HasPrefix(line, "data:") {
				continue
			}

			data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
			if data == "" || data == "[DONE]" {
				if data == "[DONE]" {
					return
				}
				continue
			}

			var chunk httpChatChunk
			if err := json.Unmarshal([]byte(data), &chunk); err != nil {
				messageChan <- &ChatMessage{
					Type:  5,
					Error: err.Error(),
				}
				continue
			}

			messageChan <- &ChatMessage{
				SessionID: chunk.SessionID,
				MessageID: chunk.MessageID,
				Type:      chunk.Type,
				Content:   chunk.Content,
				Error:     chunk.Error,
				Metadata:  chunk.Metadata,
			}
		}
	}()

	return messageChan, nil
}

func (c *AIClient) CreateAgentRun(ctx context.Context, req *AgentRunCreateRequest) (*database.AgentRun, error) {
	if c.httpBaseURL == "" {
		return nil, errors.New("agent mode requires AI runtime HTTP base URL")
	}
	payload := AgentRunCreateRequest{
		AgentDefinitionID: req.AgentDefinitionID,
		Input:             req.Input,
		TenantID:          req.TenantID,
		UserID:            req.UserID,
		SessionID:         req.SessionID,
		Metadata:          req.Metadata,
		AutoStart:         req.AutoStart,
	}

	var response runtimeAgentRunSummaryResponse
	if err := c.doJSON(ctx, http.MethodPost, "/api/v1/agents/runs", payload, req.TenantID, req.UserID, &response); err != nil {
		return nil, err
	}
	return &response.Run, nil
}

func (c *AIClient) CancelAgentRun(ctx context.Context, runID, tenantID string) (*database.AgentRun, error) {
	var response runtimeAgentRunSummaryResponse
	if err := c.doJSON(ctx, http.MethodPost, fmt.Sprintf("/api/v1/agents/runs/%s/cancel", runID), nil, tenantID, "", &response); err != nil {
		return nil, err
	}
	return &response.Run, nil
}

func (c *AIClient) ResumeAgentRun(ctx context.Context, runID, tenantID string, inputPatch json.RawMessage) (*database.AgentRun, error) {
	var response runtimeAgentRunSummaryResponse
	if err := c.doJSON(
		ctx,
		http.MethodPost,
		fmt.Sprintf("/api/v1/agents/runs/%s/resume", runID),
		runtimeAgentResumeRequest{InputPatch: inputPatch},
		tenantID,
		"",
		&response,
	); err != nil {
		return nil, err
	}
	return &response.Run, nil
}

func (c *AIClient) StreamAgentRunEvents(ctx context.Context, runID, tenantID string, afterSequence int64) (<-chan *database.AgentRunEvent, error) {
	if c.httpBaseURL == "" {
		return nil, errors.New("agent mode requires AI runtime HTTP base URL")
	}

	if c.httpClient == nil {
		c.httpClient = &http.Client{}
	}

	endpoint := c.httpBaseURL + fmt.Sprintf(
		"/api/v1/agents/runs/%s/events?stream=true&after_sequence=%d",
		url.PathEscape(runID),
		afterSequence,
	)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Accept", "text/event-stream")
	if tenantID != "" {
		httpReq.Header.Set("X-Tenant-ID", tenantID)
	}

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, err
	}

	out := make(chan *database.AgentRunEvent, 100)
	go func() {
		defer close(out)
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			log.Printf("[AIClient] agent event stream failed: status=%d", resp.StatusCode)
			return
		}

		reader := bufio.NewReader(resp.Body)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				if errors.Is(err, io.EOF) || errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
					return
				}
				log.Printf("[AIClient] agent event stream read error: %v", err)
				return
			}

			line = strings.TrimRight(line, "\r\n")
			if line == "" || !strings.HasPrefix(line, "data:") {
				continue
			}
			data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
			if data == "" || data == "[DONE]" {
				if data == "[DONE]" {
					return
				}
				continue
			}

			var event database.AgentRunEvent
			if err := json.Unmarshal([]byte(data), &event); err != nil {
				log.Printf("[AIClient] failed to parse agent event: %v", err)
				continue
			}
			out <- &event
		}
	}()

	return out, nil
}

func (c *AIClient) doJSON(
	ctx context.Context,
	method, path string,
	payload any,
	tenantID, userID string,
	out any,
) error {
	if c.httpBaseURL == "" {
		return errors.New("AI runtime HTTP base URL is empty")
	}
	if c.httpClient == nil {
		c.httpClient = &http.Client{}
	}

	var body io.Reader
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(encoded)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.httpBaseURL+path, body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if tenantID != "" {
		req.Header.Set("X-Tenant-ID", tenantID)
	}
	if userID != "" {
		req.Header.Set("X-User-ID", userID)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("runtime request failed: status=%d body=%s", resp.StatusCode, strings.TrimSpace(string(respBody)))
	}

	if out == nil {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}
