package grpc

import (
	"context"
	"io"
	"log"
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
}

// AIClient handles gRPC communication with Python AI Runtime
type AIClient struct {
	conn    *grpc.ClientConn
	client  pb.ChatServiceClient
	address string
}

// NewAIClient creates a new AI client
func NewAIClient(address string) (*AIClient, error) {
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
	return c.conn.Close()
}

// StreamChat streams chat with AI runtime using real gRPC
func (c *AIClient) StreamChat(ctx context.Context, req *ChatRequest) (<-chan *ChatMessage, error) {
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
