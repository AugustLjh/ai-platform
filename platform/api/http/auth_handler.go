package http

import (
	"encoding/json"
	"net/http"

	"github.com/ai-platform/platform/auth"
	"github.com/ai-platform/platform/middleware"
)

// AuthHandler handles authentication HTTP requests
type AuthHandler struct {
	authService *auth.AuthService
}

// NewAuthHandler creates a new auth handler
func NewAuthHandler(authService *auth.AuthService) *AuthHandler {
	return &AuthHandler{
		authService: authService,
	}
}

// HandleRegister handles user registration
func (h *AuthHandler) HandleRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Parse request
	var req auth.RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "请求数据格式错误", http.StatusBadRequest)
		return
	}

	// Register user
	resp, err := h.authService.Register(&req)
	if err != nil {
		statusCode := http.StatusInternalServerError
		if err == auth.ErrUserAlreadyExists {
			statusCode = http.StatusConflict
		} else if err.Error() == "邮箱不能为空" ||
			err.Error() == "邮箱格式不正确" ||
			err.Error() == "密码不能为空" ||
			err.Error() == "密码长度至少为8个字符" ||
			err.Error() == "密码必须包含至少一个大写字母" ||
			err.Error() == "密码必须包含至少一个小写字母" ||
			err.Error() == "密码必须包含至少一个数字" {
			statusCode = http.StatusBadRequest
		}
		respondError(w, err.Error(), statusCode)
		return
	}

	// Return response
	respondJSON(w, resp, http.StatusCreated)
}

// HandleLogin handles user login
func (h *AuthHandler) HandleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Parse request
	var req auth.LoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "请求数据格式错误", http.StatusBadRequest)
		return
	}

	// Login user
	resp, err := h.authService.Login(&req)
	if err != nil {
		statusCode := http.StatusUnauthorized
		if err == auth.ErrInvalidCredentials {
			statusCode = http.StatusUnauthorized
		}
		respondError(w, err.Error(), statusCode)
		return
	}

	// Return response
	respondJSON(w, resp, http.StatusOK)
}

// HandleRefresh handles token refresh
func (h *AuthHandler) HandleRefresh(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Parse request
	var req struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "请求数据格式错误", http.StatusBadRequest)
		return
	}

	if req.RefreshToken == "" {
		respondError(w, "刷新令牌不能为空", http.StatusBadRequest)
		return
	}

	// Refresh token
	resp, err := h.authService.RefreshToken(req.RefreshToken)
	if err != nil {
		respondError(w, "刷新令牌无效或已过期", http.StatusUnauthorized)
		return
	}

	// Return response
	respondJSON(w, resp, http.StatusOK)
}

// HandleMe returns current user info
func (h *AuthHandler) HandleMe(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// Get user from context (set by auth middleware)
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "未授权访问", http.StatusUnauthorized)
		return
	}

	// Return user info
	respondJSON(w, map[string]interface{}{
		"id":        user.ID,
		"email":     user.Email,
		"tenant_id": user.TenantID,
		"role":      user.Role,
	}, http.StatusOK)
}

// HandleLogout handles user logout (client-side token deletion in most cases)
func (h *AuthHandler) HandleLogout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "请求方法不允许", http.StatusMethodNotAllowed)
		return
	}

	// In a JWT system, logout is typically handled client-side by deleting the token
	// For more sophisticated systems, you might want to:
	// 1. Maintain a token blacklist
	// 2. Store active sessions in Redis
	// 3. Implement token revocation

	respondJSON(w, map[string]string{
		"message": "退出登录成功，请删除本地令牌",
	}, http.StatusOK)
}

// respondJSON sends a JSON response
func respondJSON(w http.ResponseWriter, data interface{}, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(data)
}

// respondError sends a JSON error response
func respondError(w http.ResponseWriter, message string, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(map[string]string{
		"error": message,
	})
}
