package main

import (
	"errors"
	"fmt"
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
	accessTokenTTL := 24 * time.Hour
	refreshTokenTTL := 24 * time.Hour * 7

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

	log.Printf("Connecting to AI Runtime at %s (chat transport: %s)...", aiRuntimeAddr, chatTransport)
	aiClient, err := grpc.NewAIClient(aiRuntimeAddr, aiRuntimeHttpAddr, chatTransport == "http")
	if err != nil {
		log.Fatalf("Failed to initialize AI Runtime client: %v", err)
	}
	defer aiClient.Close()

	var tokenBlacklist *database.TokenBlacklist
	var sessionCache *database.SessionCache
	var rateLimitCache *database.RateLimitCache

	if getEnvBool("REDIS_ENABLED", true) {
		redisConfig := &database.RedisConfig{
			Host:     getEnv("REDIS_HOST", "localhost"),
			Port:     getEnvInt("REDIS_PORT", 6379),
			Password: getEnv("REDIS_PASSWORD", ""),
			DB:       getEnvInt("REDIS_DB", 0),
		}
		redisClient, err := database.NewRedisClient(redisConfig)
		if err != nil {
			if getEnvBool("REDIS_REQUIRED", false) {
				log.Fatalf("Failed to connect to Redis: %v", err)
			}
			log.Printf("Redis unavailable, falling back to in-memory auth/rate limiting: %v", err)
		} else {
			defer func() {
				if closeErr := redisClient.Close(); closeErr != nil {
					log.Printf("Failed to close Redis client: %v", closeErr)
				}
			}()
			tokenBlacklist = database.NewTokenBlacklist(redisClient)
			sessionCache = database.NewSessionCache(redisClient, refreshTokenTTL)
			rateLimitCache = database.NewRateLimitCache(redisClient)
			log.Printf("Redis connected at %s:%d; distributed auth and rate limiting enabled", redisConfig.Host, redisConfig.Port)
		}
	} else {
		log.Println("Redis integration disabled; using in-memory auth and rate limiting")
	}

	// Initialize auth components
	tokenManager := auth.NewTokenManager(
		jwtSecret,
		accessTokenTTL,
		refreshTokenTTL,
	)
	userStore := database.NewPostgresUserStore(pgPool)
	authService := auth.NewAuthService(
		userStore,
		tokenManager,
		auth.WithTokenBlacklist(tokenBlacklist),
		auth.WithSessionCache(sessionCache),
	)

	demoUser := &auth.User{
		ID:       "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a12",
		Email:    "demo@example.com",
		TenantID: "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
		Role:     "user",
		Active:   true,
	}
	if err := ensureDemoUser(userStore, demoUser, "demo123456"); err != nil {
		log.Printf("Failed to sync demo user: %v", err)
	}
	log.Printf("Demo user ready: %s", demoUser.Email)

	// Initialize services
	sessionStore := database.NewSessionStore(pgPool)
	chatService := service.NewChatService(aiClient, sessionStore)
	agentStore := database.NewAgentStore(pgPool)
	subagentStore := database.NewSubagentStore(pgPool)
	skillStore := database.NewSkillStore(pgPool)
	mcpStore := database.NewMCPStore(pgPool)
	agentService := service.NewAgentService(aiClient, agentStore, subagentStore, sessionStore, skillStore, mcpStore)

	// Initialize middleware (with real JWT auth)
	authMiddleware := middleware.NewAuthMiddleware(authService)
	rateLimiter := middleware.NewRateLimiter(100, time.Minute, rateLimitCache) // 100 requests per minute
	guardMiddleware := middleware.NewGuardMiddleware()
	costTracker := middleware.NewCostTracker()
	corsMiddleware := middleware.NewCORSMiddleware() // 添加这行

	// Initialize HTTP handlers
	chatHandler := httphandler.NewChatHandler(chatService, costTracker)
	authHandler := httphandler.NewAuthHandler(authService)
	agentHandler := httphandler.NewAgentHandler(agentService)
	skillHandler := httphandler.NewSkillHandler(agentService)
	mcpHandler := httphandler.NewMCPHandler(agentService)
	subagentHandler := httphandler.NewSubagentHandler(agentService)

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

	mux.Handle("/api/v1/agents/runs/",
		chain(
			http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch {
				case strings.HasSuffix(r.URL.Path, "/tree"):
					agentHandler.HandleRunTree(w, r)
				case strings.HasSuffix(r.URL.Path, "/invocations"):
					agentHandler.HandleRunInvocations(w, r)
				case strings.HasSuffix(r.URL.Path, "/events"):
					agentHandler.HandleRunEvents(w, r)
				case strings.HasSuffix(r.URL.Path, "/cancel"):
					agentHandler.HandleCancelRun(w, r)
				case strings.HasSuffix(r.URL.Path, "/resume"):
					agentHandler.HandleResumeRun(w, r)
				default:
					agentHandler.HandleRunByID(w, r)
				}
			}),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents/runs",
		chain(
			http.HandlerFunc(agentHandler.HandleRuns),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents/tools",
		chain(
			http.HandlerFunc(agentHandler.HandleTools),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents/runtime-status",
		chain(
			http.HandlerFunc(agentHandler.HandleRuntimeStatus),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents/workspace-sources",
		chain(
			http.HandlerFunc(agentHandler.HandleWorkspaceSources),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents/workspaces/cleanup",
		chain(
			http.HandlerFunc(agentHandler.HandleCleanupWorkspaces),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents/workspaces",
		chain(
			http.HandlerFunc(agentHandler.HandleInspectWorkspaces),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents/",
		chain(
			http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch {
				case strings.HasSuffix(r.URL.Path, "/runs"):
					agentHandler.HandleCreateRun(w, r)
				case strings.HasSuffix(r.URL.Path, "/skills"):
					skillHandler.HandleUpdateAgentSkills(w, r)
				case strings.HasSuffix(r.URL.Path, "/knowledge-bases"):
					agentHandler.HandleUpdateAgentKnowledgeBases(w, r)
				case strings.HasSuffix(r.URL.Path, "/clear-context"):
					agentHandler.HandleClearAgentContext(w, r)
				case strings.HasSuffix(r.URL.Path, "/mcp-servers"):
					mcpHandler.HandleUpdateAgentMCPServers(w, r)
				case strings.HasSuffix(r.URL.Path, "/subagents"):
					subagentHandler.HandleUpdateAgentSubagents(w, r)
				default:
					agentHandler.HandleAgentByID(w, r)
				}
			}),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/agents",
		chain(
			http.HandlerFunc(agentHandler.HandleAgents),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/subagents/",
		chain(
			http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch {
				case strings.HasSuffix(r.URL.Path, "/control-plane"):
					subagentHandler.HandleSubagentControlPlane(w, r)
				case strings.HasSuffix(r.URL.Path, "/versions"):
					subagentHandler.HandleCreateSubagentVersion(w, r)
				case strings.HasSuffix(r.URL.Path, "/publication"):
					subagentHandler.HandleUpdateSubagentPublication(w, r)
				case strings.HasSuffix(r.URL.Path, "/test-runs"):
					subagentHandler.HandleSubagentTestRuns(w, r)
				default:
					subagentHandler.HandleSubagentByID(w, r)
				}
			}),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/subagents/governance",
		chain(
			http.HandlerFunc(subagentHandler.HandleSubagentGovernance),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/subagents/metadata-aliases/freeze",
		chain(
			http.HandlerFunc(subagentHandler.HandleFreezeSubagentMetadataAliases),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/subagents",
		chain(
			http.HandlerFunc(subagentHandler.HandleSubagents),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/skills/sync",
		chain(
			http.HandlerFunc(skillHandler.HandleSyncSkills),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/skills/",
		chain(
			http.HandlerFunc(skillHandler.HandleSkillByID),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/skills",
		chain(
			http.HandlerFunc(skillHandler.HandleSkills),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/mcp/servers/",
		chain(
			http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch {
				case strings.HasSuffix(r.URL.Path, "/test"):
					mcpHandler.HandleTestServer(w, r)
				case strings.HasSuffix(r.URL.Path, "/refresh-tools"):
					mcpHandler.HandleRefreshServerTools(w, r)
				default:
					mcpHandler.HandleServerByID(w, r)
				}
			}),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/mcp/governance",
		chain(
			http.HandlerFunc(mcpHandler.HandleGovernance),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/mcp/bulk-actions",
		chain(
			http.HandlerFunc(mcpHandler.HandleBulkActions),
			authMiddleware.Handler,
			rateLimiter.Handler,
			guardMiddleware.Handler,
		))

	mux.Handle("/api/v1/mcp/servers",
		chain(
			http.HandlerFunc(mcpHandler.HandleServers),
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
	mux.Handle("/api/v1/uploads/", kbHandler)
	mux.Handle("/api/v1/uploads", kbHandler)

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
	log.Println("  Credentials are managed server-side and no longer shown on the login page.")
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

func ensureDemoUser(userStore auth.UserStore, demoUser *auth.User, rawPassword string) error {
	passwordHash, err := auth.HashPassword(rawPassword)
	if err != nil {
		return fmt.Errorf("failed to hash demo user password: %w", err)
	}
	demoUser.PasswordHash = passwordHash

	existing, err := userStore.GetByEmail(demoUser.Email)
	switch {
	case errors.Is(err, auth.ErrUserNotFound):
		if err := userStore.Create(demoUser); err != nil {
			return fmt.Errorf("failed to create demo user: %w", err)
		}
		return nil
	case err != nil:
		return fmt.Errorf("failed to load demo user: %w", err)
	}

	updated := *existing
	changed := false

	if !auth.VerifyPassword(rawPassword, updated.PasswordHash) {
		updated.PasswordHash = passwordHash
		changed = true
	}
	if updated.TenantID == "" {
		updated.TenantID = demoUser.TenantID
		changed = true
	}
	if updated.Role == "" {
		updated.Role = demoUser.Role
		changed = true
	}
	if !updated.Active {
		updated.Active = true
		changed = true
	}

	if !changed {
		return nil
	}
	if err := userStore.Update(&updated); err != nil {
		return fmt.Errorf("failed to update demo user: %w", err)
	}
	return nil
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

func getEnvBool(key string, defaultValue bool) bool {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return defaultValue
	}
	switch strings.ToLower(value) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return defaultValue
	}
}
