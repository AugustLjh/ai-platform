package middleware

import (
	"log"
	"net/http"
	"sync"
	"time"
)

// CostTracker tracks API usage costs
type CostTracker struct {
	mu     sync.RWMutex
	costs  map[string]*UserCost
	prices ModelPricing
}

// UserCost tracks cost for a user
type UserCost struct {
	TotalCost      float64
	TotalTokens    int64
	RequestCount   int64
	LastUpdated    time.Time
}

// ModelPricing holds pricing information
type ModelPricing struct {
	InputTokenPrice  float64 // per 1K tokens
	OutputTokenPrice float64 // per 1K tokens
}

// NewCostTracker creates a new cost tracker
func NewCostTracker() *CostTracker {
	return &CostTracker{
		costs: make(map[string]*UserCost),
		prices: ModelPricing{
			InputTokenPrice:  0.0015,  // $0.0015 per 1K tokens
			OutputTokenPrice: 0.002,   // $0.002 per 1K tokens
		},
	}
}

// Handler returns the middleware handler
func (ct *CostTracker) Handler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Get user from context
		user, ok := GetUser(r.Context())
		if !ok {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		// Check if user has exceeded quota
		if ct.hasExceededQuota(user.ID) {
			http.Error(w, "Quota exceeded", http.StatusPaymentRequired)
			return
		}

		// Increment request count
		ct.incrementRequests(user.ID)

		next.ServeHTTP(w, r)
	})
}

// TrackTokens tracks token usage and calculates cost
func (ct *CostTracker) TrackTokens(userID string, inputTokens, outputTokens int64) {
	ct.mu.Lock()
	defer ct.mu.Unlock()

	cost, exists := ct.costs[userID]
	if !exists {
		cost = &UserCost{}
		ct.costs[userID] = cost
	}

	// Calculate cost
	inputCost := float64(inputTokens) / 1000.0 * ct.prices.InputTokenPrice
	outputCost := float64(outputTokens) / 1000.0 * ct.prices.OutputTokenPrice

	cost.TotalCost += inputCost + outputCost
	cost.TotalTokens += inputTokens + outputTokens
	cost.LastUpdated = time.Now()

	log.Printf("[Cost] User %s: +%d tokens, $%.6f (total: $%.6f)",
		userID, inputTokens+outputTokens, inputCost+outputCost, cost.TotalCost)
}

// GetCost returns cost information for a user
func (ct *CostTracker) GetCost(userID string) *UserCost {
	ct.mu.RLock()
	defer ct.mu.RUnlock()

	cost, exists := ct.costs[userID]
	if !exists {
		return &UserCost{}
	}

	// Return copy
	return &UserCost{
		TotalCost:    cost.TotalCost,
		TotalTokens:  cost.TotalTokens,
		RequestCount: cost.RequestCount,
		LastUpdated:  cost.LastUpdated,
	}
}

// hasExceededQuota checks if user has exceeded quota
func (ct *CostTracker) hasExceededQuota(userID string) bool {
	ct.mu.RLock()
	defer ct.mu.RUnlock()

	cost, exists := ct.costs[userID]
	if !exists {
		return false
	}

	// Example quota: $10 per month
	const monthlyQuota = 10.0
	return cost.TotalCost > monthlyQuota
}

// incrementRequests increments request count
func (ct *CostTracker) incrementRequests(userID string) {
	ct.mu.Lock()
	defer ct.mu.Unlock()

	cost, exists := ct.costs[userID]
	if !exists {
		cost = &UserCost{}
		ct.costs[userID] = cost
	}

	cost.RequestCount++
	cost.LastUpdated = time.Now()
}
