package middleware

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/ai-platform/platform/auth"
)

// User represents an authenticated user
type User struct {
	ID       string
	TenantID string
	Role     string
	Email    string
}

// AuthMiddleware handles JWT authentication
type AuthMiddleware struct {
	authService *auth.AuthService
}

// NewAuthMiddleware creates a new auth middleware with real JWT validation
func NewAuthMiddleware(authService *auth.AuthService) *AuthMiddleware {
	return &AuthMiddleware{
		authService: authService,
	}
}

// Handler returns the middleware handler
func (m *AuthMiddleware) Handler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Extract token from Authorization header
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			respondError(w, "Missing Authorization header", http.StatusUnauthorized)
			return
		}

		// Extract bearer token
		token := strings.TrimPrefix(authHeader, "Bearer ")
		if token == authHeader {
			respondError(w, "Invalid token format. Use: Bearer <token>", http.StatusUnauthorized)
			return
		}

		// Validate JWT token
		user, err := m.authService.ValidateToken(token)
		if err != nil {
			respondError(w, "Invalid or expired token", http.StatusUnauthorized)
			return
		}

		// Convert to middleware User type
		middlewareUser := &User{
			ID:       user.ID,
			TenantID: user.TenantID,
			Role:     user.Role,
			Email:    user.Email,
		}

		// Add user to context
		ctx := setUser(r.Context(), middlewareUser)
		r = r.WithContext(ctx)

		next.ServeHTTP(w, r)
	})
}

// Context key for user
type contextKey string

const userContextKey contextKey = "user"

// setUser adds user to context
func setUser(ctx context.Context, user *User) context.Context {
	return context.WithValue(ctx, userContextKey, user)
}

// GetUser retrieves user from context
func GetUser(ctx context.Context) (*User, bool) {
	user, ok := ctx.Value(userContextKey).(*User)
	return user, ok
}

// respondError sends a JSON error response
func respondError(w http.ResponseWriter, message string, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(map[string]string{
		"error": message,
	})
}
