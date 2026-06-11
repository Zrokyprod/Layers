// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package config

import "testing"

func TestLoadDefaultsIngestURLFromAPIURL(t *testing.T) {
	t.Setenv("ZROKY_API_URL", "http://localhost:8000/")
	t.Setenv("ZROKY_INGEST_URL", "")

	cfg := Load()

	if cfg.ZrokyIngestURL != "http://localhost:8000/api/v1/ingest" {
		t.Fatalf("ingest url = %q", cfg.ZrokyIngestURL)
	}
}

func TestLoadReadsEmitModeAndExplicitIngestURL(t *testing.T) {
	t.Setenv("ZROKY_EMIT_MODE", "HTTP")
	t.Setenv("ZROKY_INGEST_URL", "http://backend.local/ingest")
	t.Setenv("OPENAI_UPSTREAM_BASE_URL", "http://mock-openai.local/")

	cfg := Load()

	if cfg.EmitMode != "http" {
		t.Fatalf("emit mode = %q, want http", cfg.EmitMode)
	}
	if cfg.ZrokyIngestURL != "http://backend.local/ingest" {
		t.Fatalf("ingest url = %q", cfg.ZrokyIngestURL)
	}
	if cfg.OpenAIBaseURL != "http://mock-openai.local" {
		t.Fatalf("openai base url = %q", cfg.OpenAIBaseURL)
	}
}

func TestLoadReadsGatewayAuthAndProviderKeys(t *testing.T) {
	t.Setenv("ZROKY_GATEWAY_AUTH_TOKEN", "gateway-secret")
	t.Setenv("ZROKY_ALLOWED_PROJECT_IDS", "proj_1, proj_2,,")
	t.Setenv("OPENAI_API_KEY", "sk-openai")
	t.Setenv("ANTHROPIC_API_KEY", "sk-anthropic")
	t.Setenv("GOOGLE_API_KEY", "sk-google")
	t.Setenv("ZROKY_WORKFLOW_NAME", "support-resolution")
	t.Setenv("ZROKY_PROMPT_VERSION", "support-v42")

	cfg := Load()

	if cfg.GatewayAuthToken != "gateway-secret" {
		t.Fatalf("gateway auth token = %q", cfg.GatewayAuthToken)
	}
	for _, projectID := range []string{"proj_1", "proj_2"} {
		if _, ok := cfg.AllowedProjectIDs[projectID]; !ok {
			t.Fatalf("allowed project %q missing from %+v", projectID, cfg.AllowedProjectIDs)
		}
	}
	if cfg.OpenAIAPIKey != "sk-openai" || cfg.AnthropicAPIKey != "sk-anthropic" || cfg.GoogleAPIKey != "sk-google" {
		t.Fatalf("provider keys not loaded: %+v", cfg)
	}
	if cfg.WorkflowName != "support-resolution" || cfg.PromptVersion != "support-v42" {
		t.Fatalf("capture context not loaded: %+v", cfg)
	}
}

func TestLoadReadsCaptureDurabilityConfig(t *testing.T) {
	t.Setenv("ZROKY_GATEWAY_ID", "gw-1")
	t.Setenv("ZROKY_CAPTURE_DURABILITY_MODE", "warn_only")
	t.Setenv("ZROKY_SPOOL_RESERVE_BYTES", "4096")
	t.Setenv("ZROKY_SPOOL_HIGH_WATERMARK_RATIO", "0.75")
	t.Setenv("ZROKY_GATEWAY_HEARTBEAT_INTERVAL_MS", "15000")

	cfg := Load()

	if cfg.GatewayID != "gw-1" {
		t.Fatalf("gateway id = %q", cfg.GatewayID)
	}
	if cfg.CaptureDurability != "warn_only" {
		t.Fatalf("durability = %q", cfg.CaptureDurability)
	}
	if cfg.SpoolReserveBytes != 4096 {
		t.Fatalf("reserve bytes = %d", cfg.SpoolReserveBytes)
	}
	if cfg.SpoolHighWatermark != 0.75 {
		t.Fatalf("high watermark = %f", cfg.SpoolHighWatermark)
	}
	if cfg.HeartbeatInterval.Milliseconds() != 15000 {
		t.Fatalf("heartbeat interval = %s", cfg.HeartbeatInterval)
	}
}
