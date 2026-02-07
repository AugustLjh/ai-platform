package middleware

import (
	"context"
	"net/http"
	"sync"
	"time"
)

// RateLimiter implements token bucket rate limiting
type RateLimiter struct {
	mu              sync.Mutex
	buckets         map[string]*bucket
	rate            int           // requests per window
	window          time.Duration // time window
	cleanupInterval time.Duration
	ctx             context.Context
	cancel          context.CancelFunc
}

type bucket struct {
	tokens   int
	lastSeen time.Time
}

// NewRateLimiter creates a new rate limiter
func NewRateLimiter(rate int, window time.Duration) *RateLimiter {
	ctx, cancel := context.WithCancel(context.Background())
	rl := &RateLimiter{
		buckets:         make(map[string]*bucket),
		rate:            rate,
		window:          window,
		cleanupInterval: 5 * time.Minute,
		ctx:             ctx,
		cancel:          cancel,
	}

	// Start cleanup goroutine
	go rl.cleanup()

	return rl
}

// Handler returns the middleware handler
func (rl *RateLimiter) Handler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Get user/tenant ID from context for rate limiting
		key := rl.getKey(r)

		if !rl.allow(key) {
			http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// allow checks if request is allowed
func (rl *RateLimiter) allow(key string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	b, exists := rl.buckets[key]

	if !exists {
		// New bucket
		rl.buckets[key] = &bucket{
			tokens:   rl.rate - 1,
			lastSeen: now,
		}
		return true
	}

	// Refill tokens based on elapsed time
	elapsed := now.Sub(b.lastSeen)
	if elapsed >= rl.window {
		b.tokens = rl.rate
		b.lastSeen = now
	}

	// Check if tokens available
	if b.tokens > 0 {
		b.tokens--
		b.lastSeen = now
		return true
	}

	return false
}

// getKey extracts rate limit key from request
func (rl *RateLimiter) getKey(r *http.Request) string {
	// Try to get user from context
	if user, ok := GetUser(r.Context()); ok {
		return "user:" + user.ID
	}

	// Fall back to IP address
	return "ip:" + r.RemoteAddr
}

// cleanup removes old buckets periodically
func (rl *RateLimiter) cleanup() {
	ticker := time.NewTicker(rl.cleanupInterval)
	defer ticker.Stop()

	for {
		select {
		case <-rl.ctx.Done():
			return
		case <-ticker.C:
			rl.mu.Lock()
			now := time.Now()
			for key, b := range rl.buckets {
				if now.Sub(b.lastSeen) > rl.window*2 {
					delete(rl.buckets, key)
				}
			}
			rl.mu.Unlock()
		}
	}
}

// Shutdown gracefully stops the rate limiter
func (rl *RateLimiter) Shutdown() {
	rl.cancel()
}
