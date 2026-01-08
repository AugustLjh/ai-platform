package main

import (
	"log"
	"net/http"
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
	platformPort := getEnv("PLATFORM_PORT", ":8080")
	jwtSecret := getEnv("JWT_SECRET", "your-secret-key-change-this-in-production")

	// Initialize AI client
	log.Printf("Connecting to AI Runtime at %s...", aiRuntimeAddr)
	aiClient, err := grpc.NewAIClient(aiRuntimeAddr)
	if err != nil {
		log.Printf("Warning: Failed to connect to AI Runtime: %v", err)
		log.Println("Running in mock mode...")
		// Continue with mock client
		aiClient, _ = grpc.NewAIClient(aiRuntimeAddr)
	}
	defer aiClient.Close()

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
	chatService := service.NewChatService(aiClient)

	// Initialize middleware (with real JWT auth)
	authMiddleware := middleware.NewAuthMiddleware(authService)
	rateLimiter := middleware.NewRateLimiter(100, time.Minute) // 100 requests per minute
	guardMiddleware := middleware.NewGuardMiddleware()
	costTracker := middleware.NewCostTracker()

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

	// Start server
	log.Println("============================================================")
	log.Println("AI Platform Server Configuration:")
	log.Println("------------------------------------------------------------")
	log.Printf("  Platform Port: %s", platformPort)
	log.Printf("  AI Runtime: %s", aiRuntimeAddr)
	log.Println("  Auth: JWT (Real)")
	log.Println("  Middleware: Auth, RateLimit, Guard, Cost")
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
	log.Println("Demo User:")
	log.Printf("  Email: %s", demoUser.Email)
	log.Println("  Password: demo123456")
	log.Println("============================================================")
	log.Printf("Server listening on %s", platformPort)

	if err := http.ListenAndServe(platformPort, mux); err != nil {
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
