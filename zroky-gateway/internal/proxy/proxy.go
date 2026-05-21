// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

// Package proxy implements the bytes-passthrough reverse proxy core.
// It reads the full request body (up to MaxBodyBytes), forwards it to the
// upstream provider, streams the response back, then emits an IngestEventV2.
package proxy

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"time"

	"github.com/rs/zerolog"
	"github.com/zroky-ai/zroky-gateway/internal/emit"
	"github.com/zroky-ai/zroky-gateway/internal/redact"
)

// Provider describes an upstream LLM endpoint.
type Provider struct {
	Name    string // "openai" | "anthropic" | "google"
	BaseURL string
	// HeaderKey is the auth header name the provider expects.
	HeaderKey string
}

var (
	OpenAI = Provider{
		Name:      "openai",
		BaseURL:   "https://api.openai.com",
		HeaderKey: "Authorization",
	}
	Anthropic = Provider{
		Name:      "anthropic",
		BaseURL:   "https://api.anthropic.com",
		HeaderKey: "x-api-key",
	}
	Google = Provider{
		Name:      "google",
		BaseURL:   "https://generativelanguage.googleapis.com",
		HeaderKey: "x-goog-api-key",
	}
)

// Handler returns an http.Handler that proxies calls to the given provider.
func Handler(
	provider Provider,
	callType string,
	emitter *emit.Emitter,
	maxBodyBytes int64,
	logger zerolog.Logger,
) http.HandlerFunc {
	hc := &http.Client{Timeout: 120 * time.Second}

	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// ── 1. Read request body ─────────────────────────────────────────
		reqBody, err := io.ReadAll(io.LimitReader(r.Body, maxBodyBytes))
		if err != nil {
			http.Error(w, "failed to read request body", http.StatusBadRequest)
			return
		}

		// ── 2. Extract tenant / project ID from header ───────────────────
		projectID := r.Header.Get("X-Zroky-Project-Id")
		agentName := r.Header.Get("X-Zroky-Agent-Name")
		sessionID := r.Header.Get("X-Zroky-Session-Id")

		// ── 3. Extract upstream API key via Zroky key-fetch ─────────────
		upstreamKey := r.Header.Get(provider.HeaderKey)
		// In production, upstreamKey is fetched from tenant_settings on the
		// control plane; the raw header is stripped before forwarding.

		// ── 4. Forward request to upstream ───────────────────────────────
		upstreamURL := provider.BaseURL + r.URL.RequestURI()
		upstreamReq, err := http.NewRequestWithContext(r.Context(), r.Method, upstreamURL, bytes.NewReader(reqBody))
		if err != nil {
			http.Error(w, "failed to build upstream request", http.StatusInternalServerError)
			return
		}
		copyHeaders(r.Header, upstreamReq.Header, provider.HeaderKey, upstreamKey)

		resp, err := hc.Do(upstreamReq)
		latencyMS := float64(time.Since(start).Microseconds()) / 1000.0

		var status = "success"
		var statusCode = 200
		var errMsg string
		var respBody []byte

		if err != nil {
			status = "error"
			statusCode = 502
			errMsg = "upstream unreachable"
			http.Error(w, "upstream error", http.StatusBadGateway)
		} else {
			defer resp.Body.Close()
			statusCode = resp.StatusCode
			if statusCode >= 400 {
				status = "error"
			}
			// Copy response headers
			for k, vs := range resp.Header {
				for _, v := range vs {
					w.Header().Add(k, v)
				}
			}
			w.WriteHeader(statusCode)
			// Stream body back while capturing for emit
			respBody, _ = io.ReadAll(resp.Body)
			_, _ = w.Write(respBody)
		}

		// ── 5. Emit IngestEventV2 (best-effort, never blocks) ────────────
		go func() {
			ev := buildEvent(
				projectID, provider, callType, agentName, sessionID,
				latencyMS, statusCode, status, errMsg,
				reqBody, respBody,
			)
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			if emitErr := emitter.Emit(ctx, ev); emitErr != nil {
				logger.Warn().Err(emitErr).Msg("emit failed")
			}
		}()

		logger.Info().
			Str("provider", provider.Name).
			Str("call_type", callType).
			Int("status", statusCode).
			Float64("latency_ms", latencyMS).
			Str("project_id", projectID).
			Msg("proxied")
	}
}

// ── helpers ───────────────────────────────────────────────────────────────────

func copyHeaders(src, dst http.Header, authKey, upstreamKey string) {
	for k, vs := range src {
		switch k {
		case "X-Zroky-Project-Id", "X-Zroky-Agent-Name", "X-Zroky-Session-Id":
			continue // strip Zroky-internal headers
		}
		for _, v := range vs {
			dst.Add(k, v)
		}
	}
	// Inject the resolved upstream key
	if upstreamKey != "" {
		dst.Set(authKey, upstreamKey)
	}
}

func buildEvent(
	projectID string, provider Provider, callType, agentName, sessionID string,
	latencyMS float64, statusCode int, status, errMsg string,
	reqBody, respBody []byte,
) *emit.IngestEventV2 {
	model := extractModel(reqBody)
	var reqMap, respMap map[string]interface{}
	_ = json.Unmarshal(redact.Body(reqBody), &reqMap)
	_ = json.Unmarshal(redact.Body(respBody), &respMap)

	usage := extractUsage(respMap)

	return &emit.IngestEventV2{
		ProjectID:    projectID,
		Provider:     provider.Name,
		Model:        model,
		CallType:     callType,
		LatencyMS:    latencyMS,
		PromptTokens: usage.prompt,
		OutputTokens: usage.completion,
		TotalTokens:  usage.total,
		Status:       status,
		StatusCode:   statusCode,
		AgentName:    agentName,
		SessionID:    sessionID,
		RequestBody:  reqMap,
		ResponseBody: respMap,
		ErrorMessage: errMsg,
	}
}

func extractModel(body []byte) string {
	var m map[string]interface{}
	if err := json.Unmarshal(body, &m); err != nil {
		return "unknown"
	}
	if v, ok := m["model"].(string); ok && v != "" {
		return v
	}
	return "unknown"
}

type usageTokens struct{ prompt, completion, total int }

func extractUsage(resp map[string]interface{}) usageTokens {
	if resp == nil {
		return usageTokens{}
	}
	u, ok := resp["usage"].(map[string]interface{})
	if !ok {
		return usageTokens{}
	}
	toInt := func(key string) int {
		if v, ok := u[key].(float64); ok {
			return int(v)
		}
		return 0
	}
	prompt := toInt("prompt_tokens") + toInt("input_tokens")
	completion := toInt("completion_tokens") + toInt("output_tokens")
	total := toInt("total_tokens")
	if total == 0 {
		total = prompt + completion
	}
	return usageTokens{prompt, completion, total}
}
