// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

// Package emit publishes IngestEvent v2 payloads to a Redis Stream.
package emit

import (
	"context"
	"encoding/json"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/google/uuid"
)

// IngestEventV2 mirrors the Python IngestEventV2 schema.
type IngestEventV2 struct {
	EventID       string                 `json:"event_id"`
	ProjectID     string                 `json:"project_id"`
	Provider      string                 `json:"provider"`
	Model         string                 `json:"model"`
	CallType      string                 `json:"call_type"`
	TimestampUTC  string                 `json:"timestamp_utc"`
	LatencyMS     float64                `json:"latency_ms"`
	PromptTokens  int                    `json:"prompt_tokens"`
	OutputTokens  int                    `json:"output_tokens"`
	TotalTokens   int                    `json:"total_tokens"`
	CostUSD       float64                `json:"cost_usd"`
	Status        string                 `json:"status"`
	StatusCode    int                    `json:"status_code"`
	AgentName     string                 `json:"agent_name,omitempty"`
	SessionID     string                 `json:"session_id,omitempty"`
	WorkflowID    string                 `json:"workflow_id,omitempty"`
	StepIndex     *int                   `json:"step_index,omitempty"`
	AgentFramework string                `json:"agent_framework,omitempty"`
	RequestBody   map[string]interface{} `json:"request_body,omitempty"`
	ResponseBody  map[string]interface{} `json:"response_body,omitempty"`
	ErrorMessage  string                 `json:"error_message,omitempty"`
}

// Emitter writes IngestEventV2 records to a Redis Stream.
type Emitter struct {
	rdb    *redis.Client
	stream string
}

func New(rdb *redis.Client, stream string) *Emitter {
	return &Emitter{rdb: rdb, stream: stream}
}

// Emit serializes ev and appends it to the Redis Stream.
// Returns immediately on error — never blocks the proxy path.
func (e *Emitter) Emit(ctx context.Context, ev *IngestEventV2) error {
	if ev.EventID == "" {
		ev.EventID = uuid.New().String()
	}
	if ev.TimestampUTC == "" {
		ev.TimestampUTC = time.Now().UTC().Format(time.RFC3339Nano)
	}
	payload, err := json.Marshal(ev)
	if err != nil {
		return err
	}
	return e.rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: e.stream,
		Values: map[string]interface{}{
			"event": string(payload),
		},
	}).Err()
}
