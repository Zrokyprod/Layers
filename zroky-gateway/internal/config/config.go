// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all gateway configuration resolved from environment variables.
type Config struct {
	Port               string
	ReadTimeout        time.Duration
	WriteTimeout       time.Duration
	IdleTimeout        time.Duration
	RedisURL           string
	RedisStream        string
	EmitMode           string
	ZrokyAPIURL        string
	ZrokyIngestURL     string
	ZrokyHeartbeatURL  string
	ZrokyAPIKey        string // gateway-to-control-plane auth
	GatewayID          string
	GatewayAuthToken   string
	AllowedProjectIDs  map[string]struct{}
	OpenAIAPIKey       string
	AnthropicAPIKey    string
	GoogleAPIKey       string
	WorkflowName       string
	PromptVersion      string
	SpoolDir           string
	SpoolMaxBytes      int64
	SpoolFlushInterval time.Duration
	SpoolReserveBytes  int64
	SpoolHighWatermark float64
	CaptureDurability  string
	HeartbeatInterval  time.Duration
	OpenAIBaseURL      string
	AnthropicBaseURL   string
	GoogleBaseURL      string
	MaxBodyBytes       int64
	LogLevel           string
	PrettyLogs         bool
}

func Load() *Config {
	zrokyAPIURL := getenv("ZROKY_API_URL", "https://api.zroky.com")
	return &Config{
		Port:               getenv("PORT", "8090"),
		ReadTimeout:        parseDuration("READ_TIMEOUT", 30*time.Second),
		WriteTimeout:       parseDuration("WRITE_TIMEOUT", 60*time.Second),
		IdleTimeout:        parseDuration("IDLE_TIMEOUT", 120*time.Second),
		RedisURL:           getenv("REDIS_URL", "redis://localhost:6379"),
		RedisStream:        getenv("REDIS_STREAM", "zroky:ingest:v2"),
		EmitMode:           strings.ToLower(getenv("ZROKY_EMIT_MODE", "redis")),
		ZrokyAPIURL:        zrokyAPIURL,
		ZrokyIngestURL:     getenv("ZROKY_INGEST_URL", strings.TrimRight(zrokyAPIURL, "/")+"/api/v1/ingest"),
		ZrokyHeartbeatURL:  getenv("ZROKY_GATEWAY_HEARTBEAT_URL", strings.TrimRight(zrokyAPIURL, "/")+"/api/v1/capture/gateway-heartbeat"),
		ZrokyAPIKey:        getenv("ZROKY_GATEWAY_API_KEY", ""),
		GatewayID:          getenv("ZROKY_GATEWAY_ID", "gateway-local"),
		GatewayAuthToken:   getenv("ZROKY_GATEWAY_AUTH_TOKEN", ""),
		AllowedProjectIDs:  parseCSVSet("ZROKY_ALLOWED_PROJECT_IDS"),
		OpenAIAPIKey:       getenv("OPENAI_API_KEY", ""),
		AnthropicAPIKey:    getenv("ANTHROPIC_API_KEY", ""),
		GoogleAPIKey:       getenv("GOOGLE_API_KEY", ""),
		WorkflowName:       getenv("ZROKY_WORKFLOW_NAME", ""),
		PromptVersion:      getenv("ZROKY_PROMPT_VERSION", ""),
		SpoolDir:           getenv("ZROKY_SPOOL_DIR", ".zroky-spool"),
		SpoolMaxBytes:      parseInt64("ZROKY_SPOOL_MAX_BYTES", 100*1024*1024),
		SpoolFlushInterval: parseMilliseconds("ZROKY_SPOOL_FLUSH_INTERVAL_MS", 5*time.Second),
		SpoolReserveBytes:  parseInt64("ZROKY_SPOOL_RESERVE_BYTES", 8*1024*1024),
		SpoolHighWatermark: parseFloat("ZROKY_SPOOL_HIGH_WATERMARK_RATIO", 0.85),
		CaptureDurability:  strings.ToLower(getenv("ZROKY_CAPTURE_DURABILITY_MODE", "fail_closed")),
		HeartbeatInterval:  parseMilliseconds("ZROKY_GATEWAY_HEARTBEAT_INTERVAL_MS", 30*time.Second),
		OpenAIBaseURL:      strings.TrimRight(getenv("OPENAI_UPSTREAM_BASE_URL", "https://api.openai.com"), "/"),
		AnthropicBaseURL:   strings.TrimRight(getenv("ANTHROPIC_UPSTREAM_BASE_URL", "https://api.anthropic.com"), "/"),
		GoogleBaseURL:      strings.TrimRight(getenv("GOOGLE_UPSTREAM_BASE_URL", "https://generativelanguage.googleapis.com"), "/"),
		MaxBodyBytes:       parseInt64("MAX_BODY_BYTES", 4*1024*1024), // 4 MB
		LogLevel:           getenv("LOG_LEVEL", "info"),
		PrettyLogs:         getenv("PRETTY_LOGS", "false") == "true",
	}
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func parseDuration(key string, fallback time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return fallback
	}
	return d
}

func parseInt64(key string, fallback int64) int64 {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return fallback
	}
	return n
}

func parseFloat(key string, fallback float64) float64 {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.ParseFloat(v, 64)
	if err != nil || n <= 0 {
		return fallback
	}
	return n
}

func parseMilliseconds(key string, fallback time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err == nil && n > 0 {
		return time.Duration(n) * time.Millisecond
	}
	if d, err := time.ParseDuration(v); err == nil {
		return d
	}
	return fallback
}

func parseCSVSet(key string) map[string]struct{} {
	raw := os.Getenv(key)
	if raw == "" {
		return nil
	}
	out := map[string]struct{}{}
	for _, part := range strings.Split(raw, ",") {
		value := strings.TrimSpace(part)
		if value != "" {
			out[value] = struct{}{}
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}
