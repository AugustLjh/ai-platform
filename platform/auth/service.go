package auth

import (
	"errors"
	"fmt"

	"github.com/google/uuid"
)

var (
	ErrInvalidCredentials = errors.New("邮箱或密码错误")
)

// AuthService handles authentication operations
type AuthService struct {
	userStore    UserStore
	tokenManager *TokenManager
}

// NewAuthService creates a new auth service
func NewAuthService(userStore UserStore, tokenManager *TokenManager) *AuthService {
	return &AuthService{
		userStore:    userStore,
		tokenManager: tokenManager,
	}
}

// RegisterRequest represents a registration request
type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	TenantID string `json:"tenant_id,omitempty"`
	Role     string `json:"role,omitempty"`
}

// LoginRequest represents a login request
type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// AuthResponse represents an authentication response
type AuthResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"` // seconds
	User         *User  `json:"user"`
}

// Register registers a new user
func (s *AuthService) Register(req *RegisterRequest) (*AuthResponse, error) {
	// Validate request
	if err := s.validateRegisterRequest(req); err != nil {
		return nil, err
	}

	// Check if user already exists
	if _, err := s.userStore.GetByEmail(req.Email); err == nil {
		return nil, ErrUserAlreadyExists
	}

	// Hash password
	passwordHash, err := HashPassword(req.Password)
	if err != nil {
		return nil, fmt.Errorf("failed to hash password: %w", err)
	}

	// Create user
	user := &User{
		ID:           uuid.New().String(),
		Email:        req.Email,
		PasswordHash: passwordHash,
		TenantID:     req.TenantID,
		Role:         req.Role,
		Active:       true,
	}

	// Default values
	if user.TenantID == "" {
		user.TenantID = "tenant_" + uuid.New().String()
	}
	if user.Role == "" {
		user.Role = "user"
	}

	// Save user
	if err := s.userStore.Create(user); err != nil {
		return nil, fmt.Errorf("failed to create user: %w", err)
	}

	// Generate tokens
	return s.generateAuthResponse(user)
}

// Login authenticates a user and returns tokens
func (s *AuthService) Login(req *LoginRequest) (*AuthResponse, error) {
	// Validate request
	if req.Email == "" || req.Password == "" {
		return nil, ErrInvalidCredentials
	}

	// Get user by email
	user, err := s.userStore.GetByEmail(req.Email)
	if err != nil {
		if errors.Is(err, ErrUserNotFound) {
			return nil, ErrInvalidCredentials
		}
		return nil, err
	}

	// Check if user is active
	if !user.Active {
		return nil, errors.New("用户账号已被禁用")
	}

	// Verify password
	if !VerifyPassword(req.Password, user.PasswordHash) {
		return nil, ErrInvalidCredentials
	}

	// Generate tokens
	return s.generateAuthResponse(user)
}

// RefreshToken generates a new access token from refresh token
func (s *AuthService) RefreshToken(refreshToken string) (*AuthResponse, error) {
	// Validate refresh token
	claims, err := s.tokenManager.ValidateToken(refreshToken)
	if err != nil {
		return nil, err
	}

	// Get user
	user, err := s.userStore.GetByID(claims.UserID)
	if err != nil {
		return nil, err
	}

	// Check if user is active
	if !user.Active {
		return nil, errors.New("用户账号已被禁用")
	}

	// Generate new access token
	accessToken, err := s.tokenManager.GenerateAccessToken(
		user.ID,
		user.TenantID,
		user.Email,
		user.Role,
	)
	if err != nil {
		return nil, err
	}

	return &AuthResponse{
		AccessToken:  accessToken,
		RefreshToken: refreshToken, // Keep same refresh token
		TokenType:    "Bearer",
		ExpiresIn:    86400, // 24 hours
		User:         user,
	}, nil
}

// ValidateToken validates a token and returns user info
func (s *AuthService) ValidateToken(tokenString string) (*User, error) {
	claims, err := s.tokenManager.ValidateToken(tokenString)
	if err != nil {
		return nil, err
	}

	// Get user to verify still exists and active
	user, err := s.userStore.GetByID(claims.UserID)
	if err != nil {
		return nil, err
	}

	if !user.Active {
		return nil, errors.New("用户账号已被禁用")
	}

	return user, nil
}

// generateAuthResponse generates authentication response with tokens
func (s *AuthService) generateAuthResponse(user *User) (*AuthResponse, error) {
	// Generate access token
	accessToken, err := s.tokenManager.GenerateAccessToken(
		user.ID,
		user.TenantID,
		user.Email,
		user.Role,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to generate access token: %w", err)
	}

	// Generate refresh token
	refreshToken, err := s.tokenManager.GenerateRefreshToken(user.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to generate refresh token: %w", err)
	}

	return &AuthResponse{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		TokenType:    "Bearer",
		ExpiresIn:    86400, // 24 hours
		User:         user,
	}, nil
}

// validateRegisterRequest validates registration request
func (s *AuthService) validateRegisterRequest(req *RegisterRequest) error {
	if req.Email == "" {
		return errors.New("邮箱不能为空")
	}

	// Validate email format
	if !isValidEmail(req.Email) {
		return errors.New("邮箱格式不正确")
	}

	if req.Password == "" {
		return errors.New("密码不能为空")
	}
	if len(req.Password) < 6 {
		return errors.New("密码长度至少为6个字符")
	}

	// Check password complexity
	if !hasUpperCase(req.Password) {
		return errors.New("密码必须包含至少一个大写字母")
	}
	if !hasLowerCase(req.Password) {
		return errors.New("密码必须包含至少一个小写字母")
	}
	if !hasDigit(req.Password) {
		return errors.New("密码必须包含至少一个数字")
	}

	return nil
}

// isValidEmail checks if email format is valid
func isValidEmail(email string) bool {
	// Simple email validation
	if len(email) < 3 || len(email) > 254 {
		return false
	}
	atIndex := -1
	for i, c := range email {
		if c == '@' {
			if atIndex != -1 {
				return false // Multiple @ symbols
			}
			atIndex = i
		}
	}
	if atIndex <= 0 || atIndex >= len(email)-1 {
		return false
	}
	return true
}

// hasUpperCase checks if string contains uppercase letter
func hasUpperCase(s string) bool {
	for _, c := range s {
		if c >= 'A' && c <= 'Z' {
			return true
		}
	}
	return false
}

// hasLowerCase checks if string contains lowercase letter
func hasLowerCase(s string) bool {
	for _, c := range s {
		if c >= 'a' && c <= 'z' {
			return true
		}
	}
	return false
}

// hasDigit checks if string contains digit
func hasDigit(s string) bool {
	for _, c := range s {
		if c >= '0' && c <= '9' {
			return true
		}
	}
	return false
}
