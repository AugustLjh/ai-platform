package main

import (
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"time"

	"github.com/ai-platform/platform/api/grpc"
	httphandler "github.com/ai-platform/platform/api/http"
	"github.com/ai-platform/platform/auth"
	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/service"
)

func main() {
	log.Println("Starting AI Platform - Go Layer...")

	// Configuration
	aiRuntimeAddr := getEnv("AI_RUNTIME_ADDR", "localhost:50051")
	aiRuntimeHttpAddr := getEnv("AI_RUNTIME_HTTP_ADDR", "http://localhost:8000")
	platformPort := getEnv("PLATFORM_PORT", ":8080")
	jwtSecret := getEnv("JWT_SECRET", "2f7a48d9e6b3c1a5f8e2b9c4d6a7f3e5b8d2e1c6a9f3d5b7e2c4a6f8d9e3b5c1")

	// Initialize AI client
	log.Printf("Connecting to AI Runtime at %s...", aiRuntimeAddr)
	aiClient, err := grpc.NewAIClient(aiRuntimeAddr)
	if err != nil {
		log.Printf("Warning: Failed to connect to AI Runtime: %v", err)
		log.Println("Chat service will not be available until AI Runtime is ready")
		// Create a nil client to avoid panic
		aiClient = nil
	} else {
		defer aiClient.Close()
	}

	// Initialize auth components
	tokenManager := auth.NewTokenManager(
		jwtSecret,
		time.Hour,      // Access token TTL: 1 hour
		24*time.Hour*7, // Refresh token TTL: 7 days
	)
	userStore := auth.NewInMemoryUserStore()
	authService := auth.NewAuthService(userStore, tokenManager)

	// Create a demo user for testing
	demoPassword, _ := auth.HashPassword("demo123456")
	demoUser := &auth.User{
		ID:           "demo-user-001",
		Email:        "demo@example.com",
		PasswordHash: demoPassword,
		TenantID:     "demo-tenant",
		Role:         "user",
		Active:       true,
	}
	userStore.Create(demoUser)
	log.Printf("Created demo user: %s / demo123456", demoUser.Email)

	// Initialize services
	var chatService *service.ChatService
	if aiClient != nil {
		chatService = service.NewChatService(aiClient)
	}

	// Initialize middleware (with real JWT auth)
	authMiddleware := middleware.NewAuthMiddleware(authService)
	rateLimiter := middleware.NewRateLimiter(100, time.Minute) // 100 requests per minute
	guardMiddleware := middleware.NewGuardMiddleware()
	costTracker := middleware.NewCostTracker()
	corsMiddleware := middleware.NewCORSMiddleware() // 添加这行

	// Initialize HTTP handlers
	var chatHandler *httphandler.ChatHandler
	if chatService != nil {
		chatHandler = httphandler.NewChatHandler(chatService, costTracker)
	}
	authHandler := httphandler.NewAuthHandler(authService)

	// Setup routes
	mux := http.NewServeMux()

	// Health check
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})

	// Auth endpoints (no auth required)
	mux.HandleFunc("/api/v1/auth/register", authHandler.HandleRegister)
	mux.HandleFunc("/api/v1/auth/login", authHandler.HandleLogin)
	mux.HandleFunc("/api/v1/auth/refresh", authHandler.HandleRefresh)

	// Protected auth endpoints
	mux.Handle("/api/v1/auth/me",
		chain(
			http.HandlerFunc(authHandler.HandleMe),
			authMiddleware.Handler,
		))
	mux.Handle("/api/v1/auth/logout",
		chain(
			http.HandlerFunc(authHandler.HandleLogout),
			authMiddleware.Handler,
		))

	// Chat endpoints (with full middleware) - only if chat service is available
	if chatHandler != nil {
		mux.Handle("/api/v1/chat/sse",
			chain(
				http.HandlerFunc(chatHandler.HandleSSE),
				authMiddleware.Handler,
				rateLimiter.Handler,
				guardMiddleware.Handler,
				costTracker.Handler,
			))

		mux.Handle("/api/v1/chat/ws",
			chain(
				http.HandlerFunc(chatHandler.HandleWebSocket),
				authMiddleware.Handler,
				rateLimiter.Handler,
				guardMiddleware.Handler,
				costTracker.Handler,
			))

		mux.Handle("/api/v1/chat",
			chain(
				http.HandlerFunc(chatHandler.HandleChatSync),
				authMiddleware.Handler,
				rateLimiter.Handler,
				guardMiddleware.Handler,
				costTracker.Handler,
			))
	} else {
		// Return service unavailable for chat endpoints
		unavailableHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte(`{"error": "Chat service is not available. AI Runtime is not connected."}`))
		})
		mux.Handle("/api/v1/chat/sse", unavailableHandler)
		mux.Handle("/api/v1/chat/ws", unavailableHandler)
		mux.Handle("/api/v1/chat", unavailableHandler)
	}

	// Knowledge Base endpoints - proxy to AI Runtime HTTP server
	aiRuntimeUrl, err := url.Parse(aiRuntimeHttpAddr)
	if err != nil {
		log.Fatalf("Invalid AI_RUNTIME_HTTP_ADDR: %v", err)
	}
	kbProxy := httputil.NewSingleHostReverseProxy(aiRuntimeUrl)
	kbProxy.Director = func(req *http.Request) {
		req.URL.Scheme = aiRuntimeUrl.Scheme
		req.URL.Host = aiRuntimeUrl.Host
		req.URL.Path = req.URL.Path // Keep the original path
		req.Header.Set("X-Forwarded-Host", req.Host)
		req.Header.Set("X-Origin-Host", aiRuntimeUrl.Host)
	}

	// Add knowledge base routes with middleware
	mux.Handle("/api/v1/knowledge/",
		chain(
			http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				// Get user from context
				user, ok := middleware.GetUser(r.Context())
				if ok {
					// Add user info to request headers
					r.Header.Set("X-User-ID", user.ID)
					r.Header.Set("X-Tenant-ID", user.TenantID)
				}
				kbProxy.ServeHTTP(w, r)
			}),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	// Start server
	log.Println("============================================================")
	log.Println("AI Platform Server Configuration:")
	log.Println("------------------------------------------------------------")
	log.Printf("  Platform Port: %s", platformPort)
	log.Printf("  AI Runtime gRPC: %s", aiRuntimeAddr)
	log.Printf("  AI Runtime HTTP: %s", aiRuntimeHttpAddr)
	log.Println("  Auth: JWT (Real)")
	log.Println("  Middleware: CORS, Auth, RateLimit, Guard, Cost") // 更新这行
	log.Println("")
	log.Println("Auth Endpoints:")
	log.Println("  - POST /api/v1/auth/register")
	log.Println("  - POST /api/v1/auth/login")
	log.Println("  - POST /api/v1/auth/refresh")
	log.Println("  - GET  /api/v1/auth/me (protected)")
	log.Println("  - POST /api/v1/auth/logout (protected)")
	log.Println("")
	log.Println("Chat Endpoints:")
	log.Println("  - POST /api/v1/chat (sync)")
	log.Println("  - POST /api/v1/chat/sse (streaming)")
	log.Println("  - WS   /api/v1/chat/ws (websocket)")
	log.Println("")
	log.Println("Knowledge Base Endpoints (proxied to AI Runtime):")
	log.Println("  - GET    /api/v1/knowledge/documents")
	log.Println("  - POST   /api/v1/knowledge/documents")
	log.Println("  - GET    /api/v1/knowledge/documents/{id}")
	log.Println("  - PUT    /api/v1/knowledge/documents/{id}")
	log.Println("  - DELETE /api/v1/knowledge/documents/{id}")
	log.Println("  - POST   /api/v1/knowledge/documents/search")
	log.Println("  - POST   /api/v1/knowledge/documents/upload")
	log.Println("  - POST   /api/v1/knowledge/documents/from-url")
	log.Println("  - POST   /api/v1/knowledge/documents/batch")
	log.Println("  - GET    /api/v1/knowledge/stats")
	log.Println("")
	log.Println("Demo User:")
	log.Printf("  Email: %s", demoUser.Email)
	log.Println("  Password: demo123456")
	log.Println("============================================================")
	log.Printf("Server listening on %s", platformPort)

	// 应用全局CORS中间件
	if err := http.ListenAndServe(platformPort, corsMiddleware.Handler(mux)); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

// chain applies middleware in reverse order
func chain(handler http.Handler, middlewares ...func(http.Handler) http.Handler) http.Handler {
	for i := len(middlewares) - 1; i >= 0; i-- {
		handler = middlewares[i](handler)
	}
	return handler
}

// getEnv gets environment variable with default value
func getEnv(key, defaultValue string) string {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	return value
}