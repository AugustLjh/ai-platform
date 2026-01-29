package auth

import (
	"errors"
	"sync"
	"time"

	"golang.org/x/crypto/bcrypt"
)

var (
	ErrUserNotFound      = errors.New("用户不存在")
	ErrUserAlreadyExists = errors.New("该邮箱已被注册")
	ErrInvalidPassword   = errors.New("密码错误")
)

// User represents a user in the system
type User struct {
	ID           string    `json:"id"`
	Email        string    `json:"email"`
	PasswordHash string    `json:"-"` // Never expose password hash
	TenantID     string    `json:"tenant_id"`
	Role         string    `json:"role"` // admin, user, etc.
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
	Active       bool      `json:"active"`
}

// UserStore manages user storage
type UserStore interface {
	Create(user *User) error
	GetByID(id string) (*User, error)
	GetByEmail(email string) (*User, error)
	Update(user *User) error
	Delete(id string) error
	List() ([]*User, error)
}

// InMemoryUserStore implements UserStore in memory (for development)
type InMemoryUserStore struct {
	mu    sync.RWMutex
	users map[string]*User // key: user ID
	index map[string]string // email -> user ID
}

// NewInMemoryUserStore creates a new in-memory user store
func NewInMemoryUserStore() *InMemoryUserStore {
	return &InMemoryUserStore{
		users: make(map[string]*User),
		index: make(map[string]string),
	}
}

// Create creates a new user
func (s *InMemoryUserStore) Create(user *User) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Check if email already exists
	if _, exists := s.index[user.Email]; exists {
		return ErrUserAlreadyExists
	}

	// Check if ID already exists
	if _, exists := s.users[user.ID]; exists {
		return ErrUserAlreadyExists
	}

	user.CreatedAt = time.Now()
	user.UpdatedAt = time.Now()

	s.users[user.ID] = user
	s.index[user.Email] = user.ID

	return nil
}

// GetByID retrieves a user by ID
func (s *InMemoryUserStore) GetByID(id string) (*User, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	user, exists := s.users[id]
	if !exists {
		return nil, ErrUserNotFound
	}

	// Return a copy
	userCopy := *user
	return &userCopy, nil
}

// GetByEmail retrieves a user by email
func (s *InMemoryUserStore) GetByEmail(email string) (*User, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	userID, exists := s.index[email]
	if !exists {
		return nil, ErrUserNotFound
	}

	user := s.users[userID]
	userCopy := *user
	return &userCopy, nil
}

// Update updates a user
func (s *InMemoryUserStore) Update(user *User) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	existing, exists := s.users[user.ID]
	if !exists {
		return ErrUserNotFound
	}

	// If email changed, update index
	if existing.Email != user.Email {
		delete(s.index, existing.Email)
		s.index[user.Email] = user.ID
	}

	user.UpdatedAt = time.Now()
	s.users[user.ID] = user

	return nil
}

// Delete deletes a user
func (s *InMemoryUserStore) Delete(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	user, exists := s.users[id]
	if !exists {
		return ErrUserNotFound
	}

	delete(s.users, id)
	delete(s.index, user.Email)

	return nil
}

// List returns all users
func (s *InMemoryUserStore) List() ([]*User, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	users := make([]*User, 0, len(s.users))
	for _, user := range s.users {
		userCopy := *user
		users = append(users, &userCopy)
	}

	return users, nil
}

// HashPassword hashes a password using bcrypt
func HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

// VerifyPassword verifies a password against a hash
func VerifyPassword(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}
