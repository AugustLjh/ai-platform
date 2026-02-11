package grpc

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

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
	Model       string
	Temperature float32
	MaxTokens   int32
	UseRAG      bool
	UseAgent    bool
	Tools       []string
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

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(
		ctx,
		address,
		grpc.WithTransportCredentials(insecure.NewCredentials()), // TODO: Use TLS in production
		grpc.WithBlock(),
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
			UseAgent:    req.Config.UseAgent,
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
	SessionID string         `json:"session_id"`
	Message   string         `json:"message"`
	Config    httpChatConfig `json:"config"`
}

type httpChatConfig struct {
	UseRAG      bool    `json:"use_rag"`
	UseAgent    bool    `json:"use_agent"`
	Temperature float32 `json:"temperature"`
	MaxTokens   int32   `json:"max_tokens"`
	KnowledgeBaseID string `json:"knowledge_base_id"`
}

type httpChatChunk struct {
	SessionID string            `json:"session_id"`
	MessageID string            `json:"message_id"`
	Type      int32             `json:"type"`
	Content   string            `json:"content"`
	Error     string            `json:"error"`
	Metadata  map[string]string `json:"metadata"`
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
		Message:   req.Message,
		Config: httpChatConfig{
			UseRAG:      config.UseRAG,
			UseAgent:    config.UseAgent,
			Temperature: config.Temperature,
			MaxTokens:   config.MaxTokens,
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
