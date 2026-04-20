package middleware

import (
	"log"
	"net/http"
	"strings"
)

// GuardMiddleware handles content filtering and safety checks
type GuardMiddleware struct {
	blockedPatterns []string
	enabled         bool
}

// NewGuardMiddleware creates a new guard middleware
func NewGuardMiddleware() *GuardMiddleware {
	return &GuardMiddleware{
		blockedPatterns: []string{
			// Add patterns to block
			"<script>",
			"javascript:",
			"onerror=",
		},
		enabled: true,
	}
}

// Handler returns the middleware handler
func (m *GuardMiddleware) Handler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !m.enabled {
			next.ServeHTTP(w, r)
			return
		}

		// Check request body for malicious content (simple check)
		if r.Method == http.MethodPost || r.Method == http.MethodPut {
			// In production, you would:
			// 1. Parse request body
			// 2. Check against blocklist/patterns
			// 3. Use ML-based content moderation
			// 4. Implement prompt injection detection

			// For now, check Content-Type
			contentType := r.Header.Get("Content-Type")
			if strings.Contains(contentType, "application/json") {
				// Could parse and check JSON content here
				log.Println("[Guard] Checking request content...")
			}
		}

		// Add security headers
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("X-XSS-Protection", "1; mode=block")

		next.ServeHTTP(w, r)
	})
}

// CheckContent checks content for safety
func (m *GuardMiddleware) CheckContent(content string) (bool, string) {
	contentLower := strings.ToLower(content)

	for _, pattern := range m.blockedPatterns {
		if strings.Contains(contentLower, strings.ToLower(pattern)) {
			return false, "Content contains blocked pattern: " + pattern
		}
	}

	return true, ""
}
