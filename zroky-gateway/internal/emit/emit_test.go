// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package emit

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestNormalizeEventFillsRequiredCaptureFields(t *testing.T) {
	ev := &IngestEventV2{CompletionTokens: 7}

	normalizeEvent(ev)

	if ev.SchemaVersion != "v2" {
		t.Fatalf("schema version = %q, want v2", ev.SchemaVersion)
	}
	if strings.TrimSpace(ev.CallID) == "" {
		t.Fatal("expected generated call_id")
	}
	if ev.EventID != ev.CallID+":gateway" {
		t.Fatalf("event_id = %q, want %q", ev.EventID, ev.CallID+":gateway")
	}
	if strings.TrimSpace(ev.TimestampUTC) == "" {
		t.Fatal("expected generated timestamp")
	}
	if ev.OutputTokens != 7 {
		t.Fatalf("output tokens = %d, want 7", ev.OutputTokens)
	}
}

func TestNormalizeEventPreservesLegacyOutputTokens(t *testing.T) {
	ev := &IngestEventV2{OutputTokens: 11}

	normalizeEvent(ev)

	if ev.CompletionTokens != 11 {
		t.Fatalf("completion tokens = %d, want 11", ev.CompletionTokens)
	}
}

func TestParseMode(t *testing.T) {
	tests := []struct {
		raw  string
		want Mode
	}{
		{"", ModeRedis},
		{"redis", ModeRedis},
		{"HTTP", ModeHTTP},
		{" dual ", ModeDual},
	}

	for _, tt := range tests {
		got, err := ParseMode(tt.raw)
		if err != nil {
			t.Fatalf("ParseMode(%q) returned error: %v", tt.raw, err)
		}
		if got != tt.want {
			t.Fatalf("ParseMode(%q) = %q, want %q", tt.raw, got, tt.want)
		}
	}

	if _, err := ParseMode("disk"); err == nil {
		t.Fatal("expected invalid mode to fail")
	}
}

func TestHTTPEmitterPostsCanonicalIngestBatch(t *testing.T) {
	requests := make(chan *http.Request, 1)
	bodies := make(chan []byte, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		requests <- r
		bodies <- body
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	emitter, err := NewWithOptions(Options{
		Mode:       ModeHTTP,
		IngestURL:  server.URL + "/api/v1/ingest",
		APIKey:     "zk_test",
		HTTPClient: server.Client(),
	})
	if err != nil {
		t.Fatalf("NewWithOptions returned error: %v", err)
	}

	ev := &IngestEventV2{
		CallID:           "call_123",
		ProjectID:        "proj_123",
		Provider:         "openai",
		Model:            "gpt-4o-mini",
		CallType:         "chat",
		Status:           "success",
		CompletionTokens: 3,
		OutputTokens:     3,
		TotalTokens:      9,
		ToolCalls:        []map[string]interface{}{{"id": "tool_1"}},
		ToolCallsMade:    []map[string]interface{}{{"id": "tool_1"}},
	}
	if err := emitter.Emit(context.Background(), ev); err != nil {
		t.Fatalf("Emit returned error: %v", err)
	}

	req := <-requests
	if req.URL.Path != "/api/v1/ingest" {
		t.Fatalf("path = %q, want /api/v1/ingest", req.URL.Path)
	}
	if req.Header.Get("x-api-key") != "zk_test" {
		t.Fatalf("x-api-key = %q, want zk_test", req.Header.Get("x-api-key"))
	}
	if req.Header.Get("x-project-id") != "proj_123" {
		t.Fatalf("x-project-id = %q, want proj_123", req.Header.Get("x-project-id"))
	}

	var batch struct {
		Events []map[string]interface{} `json:"events"`
	}
	if err := json.Unmarshal(<-bodies, &batch); err != nil {
		t.Fatalf("ingest batch did not unmarshal: %v", err)
	}
	if len(batch.Events) != 1 {
		t.Fatalf("events len = %d, want 1", len(batch.Events))
	}
	got := batch.Events[0]
	if got["schema_version"] != "v2" || got["event_id"] != "call_123:gateway" {
		t.Fatalf("event identity = %+v", got)
	}
	if got["completion_tokens"] != float64(3) {
		t.Fatalf("completion_tokens = %v, want 3", got["completion_tokens"])
	}
	if got["total_tokens"] != float64(9) {
		t.Fatalf("total_tokens = %v, want 9", got["total_tokens"])
	}
	if _, ok := got["output_tokens"]; ok {
		t.Fatal("direct HTTP event leaked legacy output_tokens")
	}
	if got["project_id"] != "proj_123" {
		t.Fatalf("project_id = %v, want proj_123", got["project_id"])
	}
	if _, ok := got["tool_calls_made"]; ok {
		t.Fatal("direct HTTP event leaked legacy tool_calls_made")
	}
	if _, ok := got["tool_calls"]; !ok {
		t.Fatal("direct HTTP event missing canonical tool_calls")
	}
}

func TestHTTPEmitterReturnsErrorOnNon2xx(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "nope", http.StatusUnauthorized)
	}))
	defer server.Close()

	emitter, err := NewWithOptions(Options{
		Mode:       ModeHTTP,
		IngestURL:  server.URL,
		HTTPClient: server.Client(),
	})
	if err != nil {
		t.Fatalf("NewWithOptions returned error: %v", err)
	}

	err = emitter.Emit(context.Background(), &IngestEventV2{ProjectID: "proj_123"})
	if err == nil || !strings.Contains(err.Error(), "HTTP 401") {
		t.Fatalf("Emit error = %v, want HTTP 401", err)
	}
}
