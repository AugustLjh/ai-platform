package grpc

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (fn roundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}

func TestEvaluateWebSearchQualityRulesProxiesTenantUserAndBody(t *testing.T) {
	var capturedPath string
	var capturedTenant string
	var capturedUser string
	var capturedPayload []map[string]any
	client, err := NewAIClient("", "http://runtime.local", true)
	if err != nil {
		t.Fatalf("NewAIClient returned error: %v", err)
	}
	client.httpClient = &http.Client{
		Transport: roundTripperFunc(func(r *http.Request) (*http.Response, error) {
			capturedPath = r.URL.Path
			capturedTenant = r.Header.Get("X-Tenant-ID")
			capturedUser = r.Header.Get("X-User-ID")
			if err := json.NewDecoder(r.Body).Decode(&capturedPayload); err != nil {
				t.Fatalf("failed to decode request payload: %v", err)
			}
			return &http.Response{
				StatusCode: http.StatusOK,
				Header:     http.Header{"Content-Type": []string{"application/json"}},
				Body:       io.NopCloser(strings.NewReader(`{"protocol_version":"managed-web.search-quality-suite.v1","status":"passed","total":1}`)),
				Request:    r,
			}, nil
		}),
	}

	result, err := client.EvaluateWebSearchQualityRules(
		context.Background(),
		"tenant-1",
		"user-1",
		[]map[string]any{{"name": "case-1"}},
	)
	if err != nil {
		t.Fatalf("EvaluateWebSearchQualityRules returned error: %v", err)
	}

	if capturedPath != "/api/v1/agents/web/search-quality/evaluate" {
		t.Fatalf("unexpected path %q", capturedPath)
	}
	if capturedTenant != "tenant-1" || capturedUser != "user-1" {
		t.Fatalf("missing tenant/user headers: tenant=%q user=%q", capturedTenant, capturedUser)
	}
	if len(capturedPayload) != 1 || capturedPayload[0]["name"] != "case-1" {
		t.Fatalf("unexpected payload %#v", capturedPayload)
	}
	if result["status"] != "passed" {
		t.Fatalf("unexpected result %#v", result)
	}
}
