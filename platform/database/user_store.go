package database

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/ai-platform/platform/auth"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgresUserStore implements UserStore with PostgreSQL
type PostgresUserStore struct {
	pool *pgxpool.Pool
}

// NewPostgresUserStore creates a new PostgreSQL user store
func NewPostgresUserStore(pool *pgxpool.Pool) *PostgresUserStore {
	return &PostgresUserStore{
		pool: pool,
	}
}

// Create creates a new user
func (s *PostgresUserStore) Create(user *auth.User) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if user.TenantID != "" {
		tenantName := fmt.Sprintf("Tenant %s", user.TenantID)
		if user.Email != "" {
			tenantName = user.Email
		}
		if err := s.ensureTenant(ctx, user.TenantID, tenantName); err != nil {
			return err
		}
	}

	query := `
		INSERT INTO users (id, email, password_hash, tenant_id, role, active, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`

	now := time.Now()
	if user.CreatedAt.IsZero() {
		user.CreatedAt = now
	}
	if user.UpdatedAt.IsZero() {
		user.UpdatedAt = now
	}

	_, err := s.pool.Exec(ctx, query,
		user.ID,
		user.Email,
		user.PasswordHash,
		user.TenantID,
		user.Role,
		user.Active,
		user.CreatedAt,
		user.UpdatedAt,
	)

	if err != nil {
		if isUniqueViolation(err) {
			return auth.ErrUserAlreadyExists
		}
		return fmt.Errorf("failed to create user: %w", err)
	}

	return nil
}

func (s *PostgresUserStore) ensureTenant(ctx context.Context, tenantID, name string) error {
	query := `
		INSERT INTO tenants (id, name, slug, active, created_at, updated_at)
		VALUES ($1, $2, $3, true, $4, $4)
		ON CONFLICT (id) DO NOTHING
	`

	now := time.Now()
	slug := "tenant-" + tenantID
	_, err := s.pool.Exec(ctx, query, tenantID, name, slug, now)
	if err != nil {
		return fmt.Errorf("failed to ensure tenant: %w", err)
	}

	return nil
}

// GetByID retrieves a user by ID
func (s *PostgresUserStore) GetByID(id string) (*auth.User, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `
		SELECT id, email, password_hash, tenant_id, role, active, created_at, updated_at
		FROM users
		WHERE id = $1
	`

	user := &auth.User{}
	err := s.pool.QueryRow(ctx, query, id).Scan(
		&user.ID,
		&user.Email,
		&user.PasswordHash,
		&user.TenantID,
		&user.Role,
		&user.Active,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, auth.ErrUserNotFound
		}
		return nil, fmt.Errorf("failed to get user by id: %w", err)
	}

	return user, nil
}

// GetByEmail retrieves a user by email
func (s *PostgresUserStore) GetByEmail(email string) (*auth.User, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `
		SELECT id, email, password_hash, tenant_id, role, active, created_at, updated_at
		FROM users
		WHERE email = $1
	`

	user := &auth.User{}
	err := s.pool.QueryRow(ctx, query, email).Scan(
		&user.ID,
		&user.Email,
		&user.PasswordHash,
		&user.TenantID,
		&user.Role,
		&user.Active,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, auth.ErrUserNotFound
		}
		return nil, fmt.Errorf("failed to get user by email: %w", err)
	}

	return user, nil
}

// Update updates a user
func (s *PostgresUserStore) Update(user *auth.User) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `
		UPDATE users
		SET email = $2, password_hash = $3, tenant_id = $4, role = $5, active = $6, updated_at = $7
		WHERE id = $1
	`

	user.UpdatedAt = time.Now()

	result, err := s.pool.Exec(ctx, query,
		user.ID,
		user.Email,
		user.PasswordHash,
		user.TenantID,
		user.Role,
		user.Active,
		user.UpdatedAt,
	)

	if err != nil {
		return fmt.Errorf("failed to update user: %w", err)
	}

	if result.RowsAffected() == 0 {
		return auth.ErrUserNotFound
	}

	return nil
}

// Delete deletes a user
func (s *PostgresUserStore) Delete(id string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `DELETE FROM users WHERE id = $1`

	result, err := s.pool.Exec(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete user: %w", err)
	}

	if result.RowsAffected() == 0 {
		return auth.ErrUserNotFound
	}

	return nil
}

// List returns all users
func (s *PostgresUserStore) List() ([]*auth.User, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	query := `
		SELECT id, email, password_hash, tenant_id, role, active, created_at, updated_at
		FROM users
		ORDER BY created_at DESC
	`

	rows, err := s.pool.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to list users: %w", err)
	}
	defer rows.Close()

	var users []*auth.User
	for rows.Next() {
		user := &auth.User{}
		err := rows.Scan(
			&user.ID,
			&user.Email,
			&user.PasswordHash,
			&user.TenantID,
			&user.Role,
			&user.Active,
			&user.CreatedAt,
			&user.UpdatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan user: %w", err)
		}
		users = append(users, user)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating users: %w", err)
	}

	return users, nil
}

// UpdateLastLogin updates the last login timestamp
func (s *PostgresUserStore) UpdateLastLogin(userID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `
		UPDATE users
		SET last_login_at = $2
		WHERE id = $1
	`

	_, err := s.pool.Exec(ctx, query, userID, time.Now())
	if err != nil {
		return fmt.Errorf("failed to update last login: %w", err)
	}

	return nil
}

// isUniqueViolation checks if error is a unique constraint violation
func isUniqueViolation(err error) bool {
	if err == nil {
		return false
	}
	// PostgreSQL error code 23505 is unique_violation
	return err.Error() == "ERROR: duplicate key value violates unique constraint (SQLSTATE 23505)"
}
