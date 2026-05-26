package service

import "testing"

func TestValidateRequestAllowsContentOnly(t *testing.T) {
	svc := &ChatService{}

	if err := svc.validateRequest(&ChatRequest{
		SessionID: "s1",
		UserID:    "u1",
		Content:   []ContentPart{{Type: "image", URL: "https://example.com/a.png"}},
	}); err != nil {
		t.Fatalf("expected content-only request to be valid, got %v", err)
	}
}

func TestDeriveTextContentPrefersExplicitMessage(t *testing.T) {
	got := deriveTextContent("hello", []ContentPart{{Type: "text", Text: "fallback"}})
	if got != "hello" {
		t.Fatalf("unexpected content: %q", got)
	}
}
