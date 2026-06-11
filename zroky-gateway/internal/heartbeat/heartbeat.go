// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package heartbeat

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"github.com/zroky-ai/zroky-gateway/internal/spool"
)

type Options struct {
	URL            string
	APIKey         string
	ProjectID      string
	GatewayID      string
	EmitMode       string
	DurabilityMode string
	Version        string
	Interval       time.Duration
	StatusFunc     func() spool.Status
	HTTPClient     *http.Client
	Logger         zerolog.Logger
}

type Payload struct {
	ProjectID              string       `json:"project_id,omitempty"`
	GatewayID              string       `json:"gateway_id"`
	EmitMode               string       `json:"emit_mode"`
	DurabilityMode         string       `json:"durability_mode"`
	CaptureStatus          string       `json:"capture_status"`
	Spool                  spool.Status `json:"spool"`
	EmitFailures           uint64       `json:"emit_failures"`
	EnqueueFailures        uint64       `json:"enqueue_failures"`
	FlushFailures          uint64       `json:"flush_failures"`
	Flushed                uint64       `json:"flushed"`
	LossCount              uint64       `json:"loss_count"`
	BackpressureRejections uint64       `json:"backpressure_rejections"`
	LastError              string       `json:"last_error,omitempty"`
	Version                string       `json:"version,omitempty"`
	CheckedAt              time.Time    `json:"checked_at"`
}

func Loop(ctx context.Context, opts Options) {
	interval := opts.Interval
	if interval <= 0 {
		interval = 30 * time.Second
	}
	_ = SendOnce(ctx, opts)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := SendOnce(ctx, opts); err != nil {
				opts.Logger.Warn().Err(err).Msg("gateway heartbeat failed")
			}
		}
	}
}

func SendOnce(ctx context.Context, opts Options) error {
	if strings.TrimSpace(opts.URL) == "" || strings.TrimSpace(opts.APIKey) == "" || opts.StatusFunc == nil {
		return nil
	}
	client := opts.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}
	status := opts.StatusFunc()
	payload := Payload{
		ProjectID:              strings.TrimSpace(opts.ProjectID),
		GatewayID:              firstNonEmpty(opts.GatewayID, "gateway-local"),
		EmitMode:               opts.EmitMode,
		DurabilityMode:         opts.DurabilityMode,
		CaptureStatus:          firstNonEmpty(status.CaptureStatus, "unknown"),
		Spool:                  status,
		EmitFailures:           status.EmitFailures,
		EnqueueFailures:        status.EnqueueFailures,
		FlushFailures:          status.FlushFailures,
		Flushed:                status.FlushedCount,
		LossCount:              status.LossCount,
		BackpressureRejections: status.Backpressure,
		LastError:              status.LastError,
		Version:                opts.Version,
		CheckedAt:              time.Now().UTC(),
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, opts.URL, bytes.NewReader(raw))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", opts.APIKey)
	if payload.ProjectID != "" {
		req.Header.Set("x-project-id", payload.ProjectID)
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &HTTPStatusError{StatusCode: resp.StatusCode}
	}
	return nil
}

type HTTPStatusError struct {
	StatusCode int
}

func (e *HTTPStatusError) Error() string {
	return http.StatusText(e.StatusCode)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}
