package spool

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/zroky-ai/zroky-gateway/internal/emit"
)

func TestEnqueueWritesSpoolEvent(t *testing.T) {
	sp, err := New(Options{Dir: t.TempDir(), MaxBytes: 1024 * 1024, Logger: zerolog.Nop()})
	if err != nil {
		t.Fatalf("New returned error: %v", err)
	}

	if err := sp.Enqueue(&emit.IngestEventV2{ProjectID: "proj_1", Provider: "openai", Model: "gpt-4o-mini"}); err != nil {
		t.Fatalf("Enqueue returned error: %v", err)
	}

	status := sp.Status()
	if status.Backlog != 1 {
		t.Fatalf("backlog = %d, want 1", status.Backlog)
	}
	if status.Bytes == 0 {
		t.Fatal("status bytes should be non-zero")
	}
}

func TestFlushOnceDrainsAfterBackendRecovers(t *testing.T) {
	fail := true
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if fail {
			http.Error(w, "down", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	emitter, err := emit.NewWithOptions(emit.Options{
		Mode:      emit.ModeHTTP,
		IngestURL: server.URL,
	})
	if err != nil {
		t.Fatalf("NewWithOptions returned error: %v", err)
	}
	sp, err := New(Options{Dir: t.TempDir(), MaxBytes: 1024 * 1024, Logger: zerolog.Nop()})
	if err != nil {
		t.Fatalf("New returned error: %v", err)
	}
	if err := sp.Enqueue(&emit.IngestEventV2{ProjectID: "proj_1", Provider: "openai", Model: "gpt-4o-mini"}); err != nil {
		t.Fatalf("Enqueue returned error: %v", err)
	}

	flushed, err := sp.FlushOnce(context.Background(), emitter)
	if err == nil || flushed != 0 {
		t.Fatalf("first flush = (%d, %v), want failed without draining", flushed, err)
	}
	if sp.Status().Backlog != 1 {
		t.Fatal("failed flush should leave event in spool")
	}

	fail = false
	flushed, err = sp.FlushOnce(context.Background(), emitter)
	if err != nil {
		t.Fatalf("second flush returned error: %v", err)
	}
	if flushed != 1 {
		t.Fatalf("flushed = %d, want 1", flushed)
	}
	if sp.Status().Backlog != 0 {
		t.Fatal("successful flush should drain spool")
	}
}

func TestEnqueueRejectsOversizedEvent(t *testing.T) {
	sp, err := New(Options{Dir: t.TempDir(), MaxBytes: 8, Logger: zerolog.Nop()})
	if err != nil {
		t.Fatalf("New returned error: %v", err)
	}

	err = sp.Enqueue(&emit.IngestEventV2{ProjectID: "proj_1", Provider: "openai", Model: "gpt-4o-mini"})
	if err == nil {
		t.Fatal("expected oversized event error")
	}
	if sp.Status().Backlog != 0 {
		t.Fatal("oversized event must not be written")
	}
}

func TestEnqueueRejectsWhenSpoolWouldExceedBound(t *testing.T) {
	sp, err := New(Options{Dir: t.TempDir(), MaxBytes: 700, Logger: zerolog.Nop()})
	if err != nil {
		t.Fatalf("New returned error: %v", err)
	}

	first := &emit.IngestEventV2{ProjectID: "proj_1", Provider: "openai", Model: "gpt-4o-mini", RequestBody: map[string]interface{}{"p": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
	if err := sp.Enqueue(first); err != nil {
		t.Fatalf("first enqueue returned error: %v", err)
	}
	second := &emit.IngestEventV2{ProjectID: "proj_1", Provider: "openai", Model: "gpt-4o-mini", RequestBody: map[string]interface{}{"p": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}
	if err := sp.Enqueue(second); err == nil {
		t.Fatal("expected full spool error")
	}
	if sp.Status().Backlog != 1 {
		t.Fatal("full spool must not trim the existing event")
	}
}

func TestFlushLoopUsesDefaultInterval(t *testing.T) {
	sp, err := New(Options{Dir: t.TempDir(), MaxBytes: 1024 * 1024, Logger: zerolog.Nop()})
	if err != nil {
		t.Fatalf("New returned error: %v", err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()
	emitter, err := emit.NewHTTP(server.URL, "")
	if err != nil {
		t.Fatalf("NewHTTP returned error: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	sp.FlushLoop(ctx, emitter, time.Millisecond)
}
