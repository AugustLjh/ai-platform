package database

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// RedisConfig holds Redis configuration
type RedisConfig struct {
	Host     string
	Port     int
	Password string
	DB       int
}

// NewRedisClient creates a new Redis client
func NewRedisClient(config *RedisConfig) (*redis.Client, error) {
	client := redis.NewClient(&redis.Options{
		Addr:         fmt.Sprintf("%s:%d", config.Host, config.Port),
		Password:     config.Password,
		DB:           config.DB,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
		PoolSize:     10,
		MinIdleConns: 5,
	})

	// Ping to verify connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to redis: %w", err)
	}

	return client, nil
}

// RedisCache implements a simple cache
type RedisCache struct {
	client *redis.Client
}

// NewRedisCache creates a new Redis cache
func NewRedisCache(client *redis.Client) *RedisCache {
	return &RedisCache{client: client}
}

// Set sets a value in cache with expiration
func (c *RedisCache) Set(ctx context.Context, key string, value interface{}, expiration time.Duration) error {
	return c.client.Set(ctx, key, value, expiration).Err()
}

// Get gets a value from cache
func (c *RedisCache) Get(ctx context.Context, key string) (string, error) {
	return c.client.Get(ctx, key).Result()
}

// Delete deletes a value from cache
func (c *RedisCache) Delete(ctx context.Context, keys ...string) error {
	return c.client.Del(ctx, keys...).Err()
}

// Exists checks if a key exists
func (c *RedisCache) Exists(ctx context.Context, keys ...string) (int64, error) {
	return c.client.Exists(ctx, keys...).Result()
}

// Expire sets expiration on a key
func (c *RedisCache) Expire(ctx context.Context, key string, expiration time.Duration) error {
	return c.client.Expire(ctx, key, expiration).Err()
}

// Increment increments a counter
func (c *RedisCache) Increment(ctx context.Context, key string) (int64, error) {
	return c.client.Incr(ctx, key).Result()
}

// Decrement decrements a counter
func (c *RedisCache) Decrement(ctx context.Context, key string) (int64, error) {
	return c.client.Decr(ctx, key).Result()
}

// SetNX sets a value only if key doesn't exist
func (c *RedisCache) SetNX(ctx context.Context, key string, value interface{}, expiration time.Duration) (bool, error) {
	return c.client.SetNX(ctx, key, value, expiration).Result()
}

// TokenBlacklist manages blacklisted JWT tokens
type TokenBlacklist struct {
	client *redis.Client
	prefix string
}

// NewTokenBlacklist creates a new token blacklist
func NewTokenBlacklist(client *redis.Client) *TokenBlacklist {
	return &TokenBlacklist{
		client: client,
		prefix: "blacklist:token:",
	}
}

// Add adds a token to the blacklist
func (b *TokenBlacklist) Add(ctx context.Context, tokenID string, expiration time.Duration) error {
	key := b.prefix + tokenID
	return b.client.Set(ctx, key, "1", expiration).Err()
}

// IsBlacklisted checks if a token is blacklisted
func (b *TokenBlacklist) IsBlacklisted(ctx context.Context, tokenID string) (bool, error) {
	key := b.prefix + tokenID
	exists, err := b.client.Exists(ctx, key).Result()
	if err != nil {
		return false, err
	}
	return exists > 0, nil
}

// Remove removes a token from blacklist
func (b *TokenBlacklist) Remove(ctx context.Context, tokenID string) error {
	key := b.prefix + tokenID
	return b.client.Del(ctx, key).Err()
}

// SessionCache manages user sessions in Redis
type SessionCache struct {
	client *redis.Client
	prefix string
	ttl    time.Duration
}

// NewSessionCache creates a new session cache
func NewSessionCache(client *redis.Client, ttl time.Duration) *SessionCache {
	return &SessionCache{
		client: client,
		prefix: "session:",
		ttl:    ttl,
	}
}

// Set stores session data
func (s *SessionCache) Set(ctx context.Context, sessionID string, data string) error {
	key := s.prefix + sessionID
	return s.client.Set(ctx, key, data, s.ttl).Err()
}

// Get retrieves session data
func (s *SessionCache) Get(ctx context.Context, sessionID string) (string, error) {
	key := s.prefix + sessionID
	return s.client.Get(ctx, key).Result()
}

// Delete removes session data
func (s *SessionCache) Delete(ctx context.Context, sessionID string) error {
	key := s.prefix + sessionID
	return s.client.Del(ctx, key).Err()
}

// Extend extends session TTL
func (s *SessionCache) Extend(ctx context.Context, sessionID string) error {
	key := s.prefix + sessionID
	return s.client.Expire(ctx, key, s.ttl).Err()
}

// RateLimitCache manages rate limiting with Redis
type RateLimitCache struct {
	client *redis.Client
	prefix string
}

// NewRateLimitCache creates a new rate limit cache
func NewRateLimitCache(client *redis.Client) *RateLimitCache {
	return &RateLimitCache{
		client: client,
		prefix: "ratelimit:",
	}
}

// Increment increments rate limit counter
func (r *RateLimitCache) Increment(ctx context.Context, key string, window time.Duration) (int64, error) {
	fullKey := r.prefix + key

	pipe := r.client.Pipeline()
	incr := pipe.Incr(ctx, fullKey)
	pipe.Expire(ctx, fullKey, window)

	_, err := pipe.Exec(ctx)
	if err != nil {
		return 0, err
	}

	return incr.Val(), nil
}

// Get gets current rate limit count
func (r *RateLimitCache) Get(ctx context.Context, key string) (int64, error) {
	fullKey := r.prefix + key
	val, err := r.client.Get(ctx, fullKey).Int64()
	if err == redis.Nil {
		return 0, nil
	}
	return val, err
}

// Reset resets rate limit counter
func (r *RateLimitCache) Reset(ctx context.Context, key string) error {
	fullKey := r.prefix + key
	return r.client.Del(ctx, fullKey).Err()
}
