// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

// Package emit publishes IngestEvent v2 payloads to configured sinks.
package emit

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/google/uuid"
)

type Mode string

const (
	ModeRedis Mode = "redis"
	ModeHTTP  Mode = "http"
	ModeDual  Mode = "dual"
)

// IngestEventV2 mirrors the Python IngestEventV2 schema.
type IngestEventV2 struct {
	SchemaVersion    string                   `json:"schema_version"`
	CallID           string                   `json:"call_id"`
	EventID          string                   `json:"event_id"`
	ProjectID        string                   `json:"project_id"`
	RequestID        string                   `json:"request_id,omitempty"`
	Provider         string                   `json:"provider"`
	Model            string                   `json:"model"`
	CallType         string                   `json:"call_type"`
	TimestampUTC     string                   `json:"timestamp_utc"`
	LatencyMS        float64                  `json:"latency_ms"`
	PromptTokens     int                      `json:"prompt_tokens"`
	CompletionTokens int                      `json:"completion_tokens"`
	OutputTokens     int                      `json:"output_tokens"`
	TotalTokens      int                      `json:"total_tokens"`
	CostUSD          float64                  `json:"cost_usd"`
	Status           string                   `json:"status"`
	StatusCode       int                      `json:"status_code"`
	AgentName        string                   `json:"agent_name,omitempty"`
	PromptVersion    string                   `json:"prompt_version,omitempty"`
	SessionID        string                   `json:"session_id,omitempty"`
	WorkflowID       string                   `json:"workflow_id,omitempty"`
	WorkflowName     string                   `json:"workflow_name,omitempty"`
	StepIndex        *int                     `json:"step_index,omitempty"`
	AgentFramework   string                   `json:"agent_framework,omitempty"`
	TraceID          string                   `json:"trace_id,omitempty"`
	ParentCallID     string                   `json:"parent_call_id,omitempty"`
	RequestBody      map[string]interface{}   `json:"request_body,omitempty"`
	ResponseBody     map[string]interface{}   `json:"response_body,omitempty"`
	ToolDefinitions  []map[string]interface{} `json:"tool_definitions,omitempty"`
	ToolCalls        []map[string]interface{} `json:"tool_calls,omitempty"`
	ToolCallsMade    []map[string]interface{} `json:"tool_calls_made,omitempty"`
	Retrieval        map[string]interface{}   `json:"retrieval,omitempty"`
	Outcome          map[string]interface{}   `json:"outcome,omitempty"`
	OutputContent    string                   `json:"output_content,omitempty"`
	FinishReason     string                   `json:"finish_reason,omitempty"`
	StopReason       string                   `json:"stop_reason,omitempty"`
	Metadata         map[string]interface{}   `json:"metadata,omitempty"`
	ErrorMessage     string                   `json:"error_message,omitempty"`
}

// Options configures an Emitter.
type Options struct {
	Mode        Mode
	RedisClient *redis.Client
	RedisStream string
	IngestURL   string
	APIKey      string
	HTTPClient  *http.Client
}

// Emitter writes IngestEventV2 records to Redis, HTTP ingest, or both.
type Emitter struct {
	mode       Mode
	rdb        *redis.Client
	stream     string
	ingestURL  string
	apiKey     string
	httpClient *http.Client
}

func New(rdb *redis.Client, stream string) *Emitter {
	return &Emitter{
		mode:       ModeRedis,
		rdb:        rdb,
		stream:     stream,
		httpClient: http.DefaultClient,
	}
}

func NewWithOptions(opts Options) (*Emitter, error) {
	mode := opts.Mode
	if mode == "" {
		mode = ModeRedis
	}
	if err := mode.Validate(); err != nil {
		return nil, err
	}
	if mode.UsesRedis() && opts.RedisClient == nil {
		return nil, errors.New("redis emit mode requires RedisClient")
	}
	if mode.UsesHTTP() && strings.TrimSpace(opts.IngestURL) == "" {
		return nil, errors.New("http emit mode requires IngestURL")
	}

	httpClient := opts.HTTPClient
	if httpClient == nil {
		httpClient = http.DefaultClient
	}

	return &Emitter{
		mode:       mode,
		rdb:        opts.RedisClient,
		stream:     opts.RedisStream,
		ingestURL:  strings.TrimSpace(opts.IngestURL),
		apiKey:     strings.TrimSpace(opts.APIKey),
		httpClient: httpClient,
	}, nil
}

func NewHTTP(ingestURL, apiKey string) (*Emitter, error) {
	return NewWithOptions(Options{
		Mode:      ModeHTTP,
		IngestURL: ingestURL,
		APIKey:    apiKey,
	})
}

func ParseMode(raw string) (Mode, error) {
	mode := Mode(strings.ToLower(strings.TrimSpace(raw)))
	if mode == "" {
		mode = ModeRedis
	}
	return mode, mode.Validate()
}

func (m Mode) Validate() error {
	switch m {
	case ModeRedis, ModeHTTP, ModeDual:
		return nil
	default:
		return fmt.Errorf("unsupported ZROKY_EMIT_MODE %q: use redis, http, or dual", m)
	}
}

func (m Mode) UsesRedis() bool {
	return m == ModeRedis || m == ModeDual
}

func (m Mode) UsesHTTP() bool {
	return m == ModeHTTP || m == ModeDual
}

// Emit serializes ev and publishes it to the configured sinks.
func (e *Emitter) Emit(ctx context.Context, ev *IngestEventV2) error {
	normalizeEvent(ev)
	payload, err := json.Marshal(ev)
	if err != nil {
		return err
	}

	var emitErr error
	if e.mode.UsesRedis() {
		emitErr = errors.Join(emitErr, e.emitRedis(ctx, payload))
	}
	if e.mode.UsesHTTP() {
		emitErr = errors.Join(emitErr, e.emitHTTP(ctx, ev))
	}
	return emitErr
}

func (e *Emitter) emitRedis(ctx context.Context, payload []byte) error {
	return e.rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: e.stream,
		Values: map[string]interface{}{
			"event": string(payload),
		},
	}).Err()
}

func canonicalHTTPEventPayload(ev *IngestEventV2) (json.RawMessage, error) {
	payload, err := json.Marshal(ev)
	if err != nil {
		return nil, err
	}
	var event map[string]interface{}
	if err := json.Unmarshal(payload, &event); err != nil {
		return nil, err
	}
	delete(event, "project_id")
	delete(event, "timestamp_utc")
	delete(event, "status_code")
	delete(event, "request_body")
	delete(event, "response_body")
	delete(event, "output_tokens")
	delete(event, "cost_usd")
	delete(event, "tool_calls_made")
	return json.Marshal(event)
}

func (e *Emitter) emitHTTP(ctx context.Context, ev *IngestEventV2) error {
	eventPayload, err := canonicalHTTPEventPayload(ev)
	if err != nil {
		return err
	}
	batchPayload, err := json.Marshal(struct {
		Events []json.RawMessage `json:"events"`
	}{
		Events: []json.RawMessage{eventPayload},
	})
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, e.ingestURL, bytes.NewReader(batchPayload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if e.apiKey != "" {
		req.Header.Set("x-api-key", e.apiKey)
	}
	if projectID := strings.TrimSpace(ev.ProjectID); projectID != "" {
		req.Header.Set("x-project-id", projectID)
	}

	resp, err := e.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("zroky ingest HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return nil
}

func normalizeEvent(ev *IngestEventV2) {
	if ev.SchemaVersion == "" {
		ev.SchemaVersion = "v2"
	}
	if ev.CallID == "" {
		ev.CallID = uuid.New().String()
	}
	if ev.EventID == "" {
		ev.EventID = ev.CallID + ":gateway"
	}
	if len(ev.ToolCalls) == 0 && len(ev.ToolCallsMade) > 0 {
		ev.ToolCalls = ev.ToolCallsMade
	}
	if len(ev.ToolCallsMade) == 0 && len(ev.ToolCalls) > 0 {
		ev.ToolCallsMade = ev.ToolCalls
	}
	if ev.TimestampUTC == "" {
		ev.TimestampUTC = time.Now().UTC().Format(time.RFC3339Nano)
	}
	if ev.CompletionTokens == 0 && ev.OutputTokens != 0 {
		ev.CompletionTokens = ev.OutputTokens
	}
	if ev.OutputTokens == 0 && ev.CompletionTokens != 0 {
		ev.OutputTokens = ev.CompletionTokens
	}
}
