package main

import (
	"errors"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/ai-platform/platform/api/grpc"
	httphandler "github.com/ai-platform/platform/api/http"
	"github.com/ai-platform/platform/auth"
	"github.com/ai-platform/platform/database"
	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/service"
)

func main() {
	log.Println("Starting AI Platform - Go Layer...")

	// Configuration
	aiRuntimeAddr := getEnv("AI_RUNTIME_ADDR", "localhost:50051")
	aiRuntimeHttpAddr := getEnv("AI_RUNTIME_HTTP_ADDR", "http://localhost:8000")
	platformPort := getEnv("PLATFORM_PORT", ":8080")
	chatTransport := strings.ToLower(getEnv("AI_RUNTIME_CHAT_TRANSPORT", "grpc"))
	if chatTransport != "http" && chatTransport != "grpc" {
		chatTransport = "grpc"
	}
	jwtSecret := getEnv("JWT_SECRET", "2f7a48d9e6b3c1a5f8e2b9c4d6a7f3e5b8d2e1c6a9f3d5b7e2c4a6f8d9e3b5c1")

	// Initialize PostgreSQL
	pgConfig := &database.PostgresConfig{
		Host:     getEnv("POSTGRES_HOST", "localhost"),
		Port:     getEnvInt("POSTGRES_PORT", 5432),
		Database: getEnv("POSTGRES_DB", "ai_platform"),
		User:     getEnv("POSTGRES_USER", "ai_platform"),
		Password: getEnv("POSTGRES_PASSWORD", ""),
		SSLMode:  getEnv("POSTGRES_SSLMODE", "disable"),
		MaxConns: int32(getEnvInt("POSTGRES_MAX_CONNS", 25)),
		MinConns: int32(getEnvInt("POSTGRES_MIN_CONNS", 5)),
	}
	pgPool, err := database.NewPostgresDB(pgConfig)
	if err != nil {
		log.Fatalf("Failed to connect to Postgres: %v", err)
	}
	defer pgPool.Close()

	// Initialize AI client
	chatHTTPAddr := ""
	if chatTransport == "http" {
		chatHTTPAddr = aiRuntimeHttpAddr
	}
	log.Printf("Connecting to AI Runtime at %s (chat transport: %s)...", aiRuntimeAddr, chatTransport)
	aiClient, err := grpc.NewAIClient(aiRuntimeAddr, chatHTTPAddr)
	if err != nil {
		log.Fatalf("Failed to initialize AI Runtime client: %v", err)
	}
	defer aiClient.Close()

	// Initialize auth components
	tokenManager := auth.NewTokenManager(
		jwtSecret,
		24*time.Hour,   // Access token TTL: 24 hours
		24*time.Hour*7, // Refresh token TTL: 7 days
	)
	userStore := database.NewPostgresUserStore(pgPool)
	authService := auth.NewAuthService(userStore, tokenManager)

	// Create a demo user for testing
	demoPassword, _ := auth.HashPassword("demo123456")
	demoUser := &auth.User{
		ID:           "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a12",
		Email:        "demo@example.com",
		PasswordHash: demoPassword,
		TenantID:     "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
		Role:         "user",
		Active:       true,
	}
	if err := userStore.Create(demoUser); err != nil && !errors.Is(err, auth.ErrUserAlreadyExists) {
		log.Printf("Failed to create demo user: %v", err)
	}
	log.Printf("Created demo user: %s / demo123456", demoUser.Email)

	// Initialize services
	sessionStore := database.NewSessionStore(pgPool)
	chatService := service.NewChatService(aiClient, sessionStore)

	// Initialize middleware (with real JWT auth)
	authMiddleware := middleware.NewAuthMiddleware(authService)
	rateLimiter := middleware.NewRateLimiter(100, time.Minute) // 100 requests per minute
	guardMiddleware := middleware.NewGuardMiddleware()
	costTracker := middleware.NewCostTracker()
	corsMiddleware := middleware.NewCORSMiddleware() // 添加这行

	// Initialize HTTP handlers
	chatHandler := httphandler.NewChatHandler(chatService, costTracker)
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

	// Chat endpoints (with full middleware)
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

	mux.Handle("/api/v1/chat/sessions",
		chain(
			http.HandlerFunc(chatHandler.HandleSessions),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/chat/history/",
		chain(
			http.HandlerFunc(chatHandler.HandleGetHistory),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/chat/session/",
		chain(
			http.HandlerFunc(chatHandler.HandleDeleteSession),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/chat/usage/stats",
		chain(
			http.HandlerFunc(chatHandler.HandleUsageStats),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/chat/feedback/low-quality",
		chain(
			http.HandlerFunc(chatHandler.HandleLowQualitySamples),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/chat/messages/",
		chain(
			http.HandlerFunc(chatHandler.HandleMessageFeedback),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

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
	// Support both /api/v1/knowledge-bases/ and /api/v1/knowledge/ paths
	kbHandler := chain(
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
	)

	mux.Handle("/api/v1/knowledge-bases/", kbHandler)
	mux.Handle("/api/v1/knowledge-bases", kbHandler)
	mux.Handle("/api/v1/knowledge/", kbHandler)
	mux.Handle("/api/v1/knowledge", kbHandler)

	// Models endpoints - proxy to AI Runtime HTTP server
	modelsProxy := httputil.NewSingleHostReverseProxy(aiRuntimeUrl)
	modelsProxy.Director = func(req *http.Request) {
		req.URL.Scheme = aiRuntimeUrl.Scheme
		req.URL.Host = aiRuntimeUrl.Host
		req.URL.Path = req.URL.Path
		req.Header.Set("X-Forwarded-Host", req.Host)
		req.Header.Set("X-Origin-Host", aiRuntimeUrl.Host)
	}

	modelsHandler := chain(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			user, ok := middleware.GetUser(r.Context())
			if ok {
				r.Header.Set("X-User-ID", user.ID)
				r.Header.Set("X-Tenant-ID", user.TenantID)
			}
			modelsProxy.ServeHTTP(w, r)
		}),
		authMiddleware.Handler,
		rateLimiter.Handler,
		guardMiddleware.Handler,
	)

	mux.Handle("/api/v1/models/", modelsHandler)
	mux.Handle("/api/v1/models", modelsHandler)

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
	log.Println("  - GET  /api/v1/chat/usage/stats")
	log.Println("  - GET  /api/v1/chat/feedback/low-quality")
	log.Println("  - POST /api/v1/chat/messages/{id}/feedback")
	log.Println("")
	log.Println("Knowledge Base Endpoints (proxied to AI Runtime):")
	log.Println("  - GET    /api/v1/knowledge-bases")
	log.Println("  - POST   /api/v1/knowledge-bases")
	log.Println("  - GET    /api/v1/knowledge-bases/{id}")
	log.Println("  - PUT    /api/v1/knowledge-bases/{id}")
	log.Println("  - DELETE /api/v1/knowledge-bases/{id}")
	log.Println("  - GET    /api/v1/knowledge-bases/{id}/indexing-settings")
	log.Println("  - PUT    /api/v1/knowledge-bases/{id}/indexing-settings")
	log.Println("  - GET    /api/v1/knowledge-bases/{id}/retrieval-settings")
	log.Println("  - PUT    /api/v1/knowledge-bases/{id}/retrieval-settings")
	log.Println("  - POST   /api/v1/knowledge-bases/{id}/retrieval-test")
	log.Println("  - GET    /api/v1/knowledge/documents")
	log.Println("  - POST   /api/v1/knowledge/documents")
	log.Println("  - GET    /api/v1/knowledge/documents/{id}")
	log.Println("  - GET    /api/v1/knowledge/documents/{id}/preview")
	log.Println("  - GET    /api/v1/knowledge/documents/{id}/segments")
	log.Println("  - PUT    /api/v1/knowledge/documents/{id}")
	log.Println("  - DELETE /api/v1/knowledge/documents/{id}")
	log.Println("  - POST   /api/v1/knowledge/documents/search")
	log.Println("  - POST   /api/v1/knowledge/documents/upload")
	log.Println("  - POST   /api/v1/knowledge/documents/from-url")
	log.Println("  - POST   /api/v1/knowledge/documents/batch")
	log.Println("  - GET    /api/v1/knowledge/stats")
	log.Println("")
	log.Println("Models Endpoints (proxied to AI Runtime):")
	log.Println("  - GET    /api/v1/models")
	log.Println("  - POST   /api/v1/models")
	log.Println("  - GET    /api/v1/models/{id}")
	log.Println("  - PUT    /api/v1/models/{id}")
	log.Println("  - DELETE /api/v1/models/{id}")
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

func getEnvInt(key string, defaultValue int) int {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return defaultValue
	}
	return parsed
}
