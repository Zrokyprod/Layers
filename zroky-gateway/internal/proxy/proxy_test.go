// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package proxy

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/zroky-ai/zroky-gateway/internal/emit"
)

func TestReadBoundedBodyRejectsOversizedRequest(t *testing.T) {
	body, tooLarge, err := readBoundedBody(strings.NewReader("abcdef"), 5)
	if err != nil {
		t.Fatalf("readBoundedBody returned error: %v", err)
	}
	if !tooLarge {
		t.Fatal("expected oversized body to be rejected")
	}
	if body != nil {
		t.Fatalf("body = %q, want nil for oversized request", body)
	}
}

func TestCopyAndCaptureStreamsFullResponseAndBoundsTelemetryCopy(t *testing.T) {
	var dst bytes.Buffer

	captured, err := copyAndCapture(&dst, strings.NewReader("streamed-response"), 8)
	if err != nil {
		t.Fatalf("copyAndCapture returned error: %v", err)
	}
	if got := dst.String(); got != "streamed-response" {
		t.Fatalf("destination = %q, want full response", got)
	}
	if got := string(captured); got != "streamed" {
		t.Fatalf("captured = %q, want bounded prefix", got)
	}
}

func TestCopyAndCaptureReturnsCapturedPrefixOnWriteError(t *testing.T) {
	captured, err := copyAndCapture(failingWriter{}, strings.NewReader("partial"), 4)
	if err == nil {
		t.Fatal("expected write error")
	}
	if got := string(captured); got != "part" {
		t.Fatalf("captured = %q, want part", got)
	}
}

func TestReadCaptureHeadersSupportsProjectAliasAndTraceFields(t *testing.T) {
	headers := http.Header{}
	headers.Set("X-Project-Id", "proj_123")
	headers.Set("X-Zroky-Call-Id", "call_123")
	headers.Set("X-Zroky-Agent-Name", "planner")
	headers.Set("X-Zroky-Prompt-Version", "support-v42")
	headers.Set("X-Zroky-Workflow-Id", "wf_1")
	headers.Set("X-Zroky-Workflow-Name", "support-resolution")
	headers.Set("X-Zroky-Step-Index", "3")
	headers.Set("X-Zroky-Trace-Id", "trace_1")
	headers.Set("X-Zroky-Parent-Call-Id", "parent_1")

	capture := readCaptureHeaders(headers)

	if capture.ProjectID != "proj_123" {
		t.Fatalf("project id = %q, want proj_123", capture.ProjectID)
	}
	if capture.CallID != "call_123" || capture.AgentName != "planner" {
		t.Fatalf("unexpected capture headers: %+v", capture)
	}
	if capture.WorkflowID != "wf_1" || capture.WorkflowName != "support-resolution" || capture.TraceID != "trace_1" || capture.ParentCallID != "parent_1" {
		t.Fatalf("missing trace/workflow headers: %+v", capture)
	}
	if capture.PromptVersion != "support-v42" {
		t.Fatalf("prompt version = %q, want support-v42", capture.PromptVersion)
	}
	if capture.StepIndex == nil || *capture.StepIndex != 3 {
		t.Fatalf("step index = %v, want 3", capture.StepIndex)
	}
}

func TestCopyHeadersStripsOnlyZrokyInternalHeaders(t *testing.T) {
	src := http.Header{}
	src.Set("X-Zroky-Project-Id", "proj_123")
	src.Set("X-Project-Id", "proj_123")
	src.Set("X-Zroky-Trace-Id", "trace_1")
	src.Set("X-Api-Key", "provider-key")
	src.Set("Content-Type", "application/json")
	dst := http.Header{}

	copyHeaders(src, dst, "x-api-key", "provider-key")

	if dst.Get("X-Zroky-Project-Id") != "" || dst.Get("X-Project-Id") != "" || dst.Get("X-Zroky-Trace-Id") != "" {
		t.Fatalf("zroky internal headers leaked upstream: %+v", dst)
	}
	if dst.Get("x-api-key") != "provider-key" {
		t.Fatalf("provider api key missing: %+v", dst)
	}
	if dst.Get("Content-Type") != "application/json" {
		t.Fatalf("content type missing: %+v", dst)
	}
}

func TestHandlerRequiresGatewayAuthTokenWhenConfigured(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("X-Zroky-Project-Id", "proj_gateway")

	rr := httptest.NewRecorder()
	handler := HandlerWithOptions(
		OpenAI,
		"chat",
		nil,
		Options{MaxBodyBytes: 1024, GatewayAuthToken: "gateway-secret"},
		zerolog.New(io.Discard),
	)
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", rr.Code)
	}
}

func TestHandlerRejectsDisallowedProject(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("X-Zroky-Project-Id", "proj_blocked")
	req.Header.Set("X-Zroky-Gateway-Token", "gateway-secret")

	rr := httptest.NewRecorder()
	handler := HandlerWithOptions(
		OpenAI,
		"chat",
		nil,
		Options{
			MaxBodyBytes:      1024,
			GatewayAuthToken:  "gateway-secret",
			AllowedProjectIDs: map[string]struct{}{"proj_allowed": {}},
		},
		zerolog.New(io.Discard),
	)
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want 403", rr.Code)
	}
}

func TestHandlerUsesConfiguredProviderAPIKey(t *testing.T) {
	ingested := make(chan []byte, 1)
	ingestServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		ingested <- body
		w.WriteHeader(http.StatusAccepted)
	}))
	defer ingestServer.Close()

	upstreamSeen := make(chan http.Header, 1)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamSeen <- r.Header.Clone()
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"chatcmpl_key","choices":[{"message":{"content":"ok"}}]}`))
	}))
	defer upstream.Close()

	emitter, err := emit.NewWithOptions(emit.Options{
		Mode:       emit.ModeHTTP,
		IngestURL:  ingestServer.URL + "/api/v1/ingest",
		APIKey:     "zk_gateway",
		HTTPClient: ingestServer.Client(),
	})
	if err != nil {
		t.Fatalf("NewWithOptions returned error: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{"model":"gpt-4o-mini"}`))
	req.Header.Set("Authorization", "Bearer caller-provider-key")
	req.Header.Set("X-Zroky-Project-Id", "proj_gateway")
	req.Header.Set("X-Zroky-Gateway-Token", "gateway-secret")

	rr := httptest.NewRecorder()
	handler := HandlerWithOptions(
		Provider{Name: "openai", BaseURL: upstream.URL, HeaderKey: "Authorization"},
		"chat",
		emitter,
		Options{
			MaxBodyBytes:      1024 * 1024,
			GatewayAuthToken:  "gateway-secret",
			AllowedProjectIDs: map[string]struct{}{"proj_gateway": {}},
			UpstreamAPIKey:    "env-provider-key",
		},
		zerolog.New(io.Discard),
	)
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rr.Code)
	}

	select {
	case headers := <-upstreamSeen:
		if headers.Get("Authorization") != "Bearer env-provider-key" {
			t.Fatalf("authorization = %q, want env provider key", headers.Get("Authorization"))
		}
		if headers.Get("X-Zroky-Gateway-Token") != "" {
			t.Fatalf("gateway token leaked upstream: %+v", headers)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for upstream request")
	}

	select {
	case <-ingested:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for ingest")
	}
}

func TestDecodeOpenAIStreamResponseExtractsTextAndUsage(t *testing.T) {
	body := strings.Join([]string{
		`data: {"id":"chatcmpl_1","choices":[{"delta":{"content":"hel"}}]}`,
		`data: {"choices":[{"delta":{"content":"lo"}}],"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}`,
		`data: [DONE]`,
		"",
	}, "\n")

	resp := decodeResponseBody([]byte(body))
	usage := extractUsage(resp)

	if extractResponseID(resp) != "chatcmpl_1" {
		t.Fatalf("response id = %q, want chatcmpl_1", extractResponseID(resp))
	}
	if usage.prompt != 5 || usage.completion != 2 || usage.total != 7 {
		t.Fatalf("usage = %+v, want 5/2/7", usage)
	}
	content := responseContent(resp)
	if content != "hello" {
		t.Fatalf("content = %q, want hello", content)
	}
}

func TestDecodeOpenAIStreamResponseExtractsToolCallsAndFinishReason(t *testing.T) {
	body := strings.Join([]string{
		`data: {"id":"chatcmpl_tool","choices":[{"delta":{"content":"checking ","tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"lookup","arguments":"{\"query\""}}]}}]}`,
		`data: {"choices":[{"delta":{"content":"now","tool_calls":[{"index":0,"function":{"arguments":":\"weather\"}"}}]}}]}`,
		`data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":12,"completion_tokens":4,"total_tokens":16}}`,
		`data: [DONE]`,
		"",
	}, "\n")

	resp := decodeResponseBody([]byte(body))
	usage := extractUsage(resp)

	if extractResponseID(resp) != "chatcmpl_tool" {
		t.Fatalf("response id = %q, want chatcmpl_tool", extractResponseID(resp))
	}
	if usage.prompt != 12 || usage.completion != 4 || usage.total != 16 {
		t.Fatalf("usage = %+v, want 12/4/16", usage)
	}
	if content := responseContent(resp); content != "checking now" {
		t.Fatalf("content = %q, want checking now", content)
	}
	if finishReason(resp) != "tool_calls" {
		t.Fatalf("finish reason = %q, want tool_calls", finishReason(resp))
	}
	toolCalls := responseToolCalls(resp)
	if len(toolCalls) != 1 {
		t.Fatalf("tool calls len = %d, want 1: %+v", len(toolCalls), toolCalls)
	}
	function, _ := toolCalls[0]["function"].(map[string]interface{})
	if toolCalls[0]["id"] != "call_1" || function["name"] != "lookup" || function["arguments"] != `{"query":"weather"}` {
		t.Fatalf("tool call = %+v, want merged lookup call", toolCalls[0])
	}
}

func TestDecodeAnthropicStreamResponseExtractsTextAndUsage(t *testing.T) {
	body := strings.Join([]string{
		`data: {"type":"message_start","message":{"id":"msg_1","usage":{"input_tokens":8}}}`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hel"}}`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}`,
		`data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"},"usage":{"output_tokens":2}}`,
		"",
	}, "\n")

	resp := decodeResponseBody([]byte(body))
	usage := extractUsage(resp)

	if extractResponseID(resp) != "msg_1" {
		t.Fatalf("response id = %q, want msg_1", extractResponseID(resp))
	}
	if usage.prompt != 8 || usage.completion != 2 || usage.total != 10 {
		t.Fatalf("usage = %+v, want 8/2/10", usage)
	}
	if content := responseContent(resp); content != "hello" {
		t.Fatalf("content = %q, want hello", content)
	}
	if stopReason(resp) != "max_tokens" {
		t.Fatalf("stop reason = %q, want max_tokens", stopReason(resp))
	}
}

func TestDecodeOpenAIResponsesStreamExtractsTextAndUsage(t *testing.T) {
	body := strings.Join([]string{
		`data: {"type":"response.created","response":{"id":"resp_1"}}`,
		`data: {"type":"response.output_text.delta","delta":"hel"}`,
		`data: {"type":"response.output_text.delta","delta":"lo"}`,
		`data: {"type":"response.completed","response":{"id":"resp_1","status":"completed","usage":{"input_tokens":6,"output_tokens":2,"total_tokens":8}}}`,
		"",
	}, "\n")

	resp := decodeResponseBody([]byte(body))
	usage := extractUsage(resp)

	if extractResponseID(resp) != "resp_1" {
		t.Fatalf("response id = %q, want resp_1", extractResponseID(resp))
	}
	if usage.prompt != 6 || usage.completion != 2 || usage.total != 8 {
		t.Fatalf("usage = %+v, want 6/2/8", usage)
	}
	if content := responseContent(resp); content != "hello" {
		t.Fatalf("content = %q, want hello", content)
	}
}

func TestBuildEventIncludesCanonicalCaptureFields(t *testing.T) {
	step := 4
	reqBody := []byte(`{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}`)
	respBody := []byte(`{"id":"chatcmpl_1","usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7},"choices":[{"message":{"content":"done"}}]}`)

	ev := buildEvent(
		captureHeaders{
			ProjectID:      "proj_123",
			CallID:         "call_123",
			AgentName:      "planner",
			PromptVersion:  "support-v42",
			SessionID:      "sess_1",
			WorkflowID:     "wf_1",
			WorkflowName:   "support-resolution",
			AgentFramework: "custom",
			TraceID:        "trace_1",
			ParentCallID:   "parent_1",
			StepIndex:      &step,
		},
		OpenAI,
		"chat",
		12.5,
		200,
		"success",
		"",
		reqBody,
		respBody,
	)

	if ev.SchemaVersion != "v2" || ev.CallID != "call_123" || ev.ProjectID != "proj_123" {
		t.Fatalf("bad event identity: %+v", ev)
	}
	if ev.RequestID != "chatcmpl_1" {
		t.Fatalf("request id = %q, want chatcmpl_1", ev.RequestID)
	}
	if ev.PromptTokens != 5 || ev.CompletionTokens != 2 || ev.TotalTokens != 7 {
		t.Fatalf("usage = %d/%d/%d, want 5/2/7", ev.PromptTokens, ev.CompletionTokens, ev.TotalTokens)
	}
	if ev.WorkflowID != "wf_1" || ev.WorkflowName != "support-resolution" || ev.TraceID != "trace_1" || ev.ParentCallID != "parent_1" {
		t.Fatalf("missing trace fields: %+v", ev)
	}
	if ev.PromptVersion != "support-v42" {
		t.Fatalf("prompt version = %q, want support-v42", ev.PromptVersion)
	}
	if ev.OutputContent != "done" {
		t.Fatalf("output content = %q, want done", ev.OutputContent)
	}
	if ev.Metadata["source"] != "gateway_http_direct" || ev.Metadata["status_code"] != 200 {
		t.Fatalf("metadata = %+v", ev.Metadata)
	}
	if ev.StepIndex == nil || *ev.StepIndex != 4 {
		t.Fatalf("step index = %v, want 4", ev.StepIndex)
	}
	if _, err := json.Marshal(ev); err != nil {
		t.Fatalf("event did not marshal to JSON: %v", err)
	}
}

func TestHandlerProxiesAndEmitsDirectHTTPBatch(t *testing.T) {
	type ingestRecord struct {
		headers http.Header
		body    []byte
	}
	ingested := make(chan ingestRecord, 1)
	ingestServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		ingested <- ingestRecord{headers: r.Header.Clone(), body: body}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer ingestServer.Close()

	upstreamSeen := make(chan http.Header, 1)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamSeen <- r.Header.Clone()
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"chatcmpl_gateway","usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7},"choices":[{"message":{"content":"done"}}]}`))
	}))
	defer upstream.Close()

	emitter, err := emit.NewWithOptions(emit.Options{
		Mode:       emit.ModeHTTP,
		IngestURL:  ingestServer.URL + "/api/v1/ingest",
		APIKey:     "zk_gateway",
		HTTPClient: ingestServer.Client(),
	})
	if err != nil {
		t.Fatalf("NewWithOptions returned error: %v", err)
	}

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/chat/completions",
		strings.NewReader(`{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}`),
	)
	req.Header.Set("Authorization", "Bearer provider-key")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Zroky-Project-Id", "proj_gateway")
	req.Header.Set("X-Zroky-Call-Id", "call_gateway")
	req.Header.Set("X-Zroky-Agent-Name", "planner")
	req.Header.Set("X-Zroky-Prompt-Version", "support-v42")
	req.Header.Set("X-Zroky-Trace-Id", "trace_gateway")
	req.Header.Set("X-Zroky-Workflow-Name", "support-resolution")

	rr := httptest.NewRecorder()
	handler := Handler(
		Provider{Name: "openai", BaseURL: upstream.URL, HeaderKey: "Authorization"},
		"chat",
		emitter,
		1024*1024,
		zerolog.New(io.Discard),
	)
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("gateway status = %d, body %q", rr.Code, rr.Body.String())
	}

	select {
	case headers := <-upstreamSeen:
		if hasZrokyInternalHeaders(headers) {
			t.Fatalf("zroky headers leaked upstream: %+v", headers)
		}
		if headers.Get("Authorization") != "Bearer provider-key" {
			t.Fatalf("provider auth header = %q", headers.Get("Authorization"))
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for upstream request")
	}

	var record ingestRecord
	select {
	case record = <-ingested:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for direct HTTP ingest")
	}

	if record.headers.Get("x-api-key") != "zk_gateway" {
		t.Fatalf("x-api-key = %q, want zk_gateway", record.headers.Get("x-api-key"))
	}
	if record.headers.Get("x-project-id") != "proj_gateway" {
		t.Fatalf("x-project-id = %q, want proj_gateway", record.headers.Get("x-project-id"))
	}

	var batch struct {
		Events []emit.IngestEventV2 `json:"events"`
	}
	if err := json.Unmarshal(record.body, &batch); err != nil {
		t.Fatalf("ingest batch did not unmarshal: %v", err)
	}
	if len(batch.Events) != 1 {
		t.Fatalf("events len = %d, want 1", len(batch.Events))
	}
	ev := batch.Events[0]
	if ev.CallID != "call_gateway" || ev.EventID != "call_gateway:gateway" {
		t.Fatalf("event identity = %+v", ev)
	}
	if ev.ProjectID != "proj_gateway" {
		t.Fatalf("project_id = %q, want proj_gateway", ev.ProjectID)
	}
	if ev.AgentName != "planner" || ev.TraceID != "trace_gateway" {
		t.Fatalf("event context missing: %+v", ev)
	}
	if ev.WorkflowName != "support-resolution" || ev.PromptVersion != "support-v42" {
		t.Fatalf("workflow/prompt version missing: %+v", ev)
	}
	if ev.RequestID != "chatcmpl_gateway" || ev.PromptTokens != 5 || ev.CompletionTokens != 2 || ev.TotalTokens != 7 {
		t.Fatalf("event response fields wrong: %+v", ev)
	}
	if ev.Metadata["source"] != "gateway_http_direct" || ev.OutputContent != "done" {
		t.Fatalf("event metadata/output wrong: %+v", ev)
	}
}

func TestHandlerStreamsSSEAndEmitsCapturedTelemetry(t *testing.T) {
	type ingestRecord struct {
		body []byte
	}
	ingested := make(chan ingestRecord, 1)
	ingestServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		ingested <- ingestRecord{body: body}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer ingestServer.Close()

	streamBody := strings.Join([]string{
		`data: {"id":"chatcmpl_stream","choices":[{"delta":{"content":"hel"}}]}`,
		`data: {"choices":[{"delta":{"content":"lo"}}]}`,
		`data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}`,
		`data: [DONE]`,
		"",
	}, "\n")
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte(streamBody))
		if flusher, ok := w.(http.Flusher); ok {
			flusher.Flush()
		}
	}))
	defer upstream.Close()

	emitter, err := emit.NewWithOptions(emit.Options{
		Mode:       emit.ModeHTTP,
		IngestURL:  ingestServer.URL + "/api/v1/ingest",
		APIKey:     "zk_gateway",
		HTTPClient: ingestServer.Client(),
	})
	if err != nil {
		t.Fatalf("NewWithOptions returned error: %v", err)
	}

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/chat/completions",
		strings.NewReader(`{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}`),
	)
	req.Header.Set("Authorization", "Bearer provider-key")
	req.Header.Set("X-Zroky-Project-Id", "proj_gateway")
	req.Header.Set("X-Zroky-Call-Id", "call_stream")

	rr := httptest.NewRecorder()
	handler := Handler(
		Provider{Name: "openai", BaseURL: upstream.URL, HeaderKey: "Authorization"},
		"streaming",
		emitter,
		1024*1024,
		zerolog.New(io.Discard),
	)
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("gateway status = %d, body %q", rr.Code, rr.Body.String())
	}
	if rr.Body.String() != streamBody {
		t.Fatalf("stream body = %q, want %q", rr.Body.String(), streamBody)
	}

	var record ingestRecord
	select {
	case record = <-ingested:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for direct HTTP ingest")
	}

	var batch struct {
		Events []emit.IngestEventV2 `json:"events"`
	}
	if err := json.Unmarshal(record.body, &batch); err != nil {
		t.Fatalf("ingest batch did not unmarshal: %v", err)
	}
	if len(batch.Events) != 1 {
		t.Fatalf("events len = %d, want 1", len(batch.Events))
	}
	ev := batch.Events[0]
	if ev.RequestID != "chatcmpl_stream" || ev.OutputContent != "hello" {
		t.Fatalf("event response fields wrong: %+v", ev)
	}
	if ev.PromptTokens != 5 || ev.CompletionTokens != 2 || ev.TotalTokens != 7 {
		t.Fatalf("event usage wrong: %+v", ev)
	}
	if ev.FinishReason != "stop" || ev.StopReason != "stop" {
		t.Fatalf("finish/stop reason wrong: %+v", ev)
	}
	if ev.CallType != "streaming" || ev.Metadata["source"] != "gateway_http_direct" {
		t.Fatalf("event context wrong: %+v", ev)
	}
}

func responseContent(resp map[string]interface{}) string {
	choices, _ := resp["choices"].([]interface{})
	if len(choices) == 0 {
		return ""
	}
	first, _ := choices[0].(map[string]interface{})
	message, _ := first["message"].(map[string]interface{})
	content, _ := message["content"].(string)
	return content
}

func hasZrokyInternalHeaders(headers http.Header) bool {
	for key := range headers {
		normalized := strings.ToLower(key)
		if strings.HasPrefix(normalized, "x-zroky-") || normalized == "x-project-id" {
			return true
		}
	}
	return false
}

type failingWriter struct{}

func (failingWriter) Write(_ []byte) (int, error) {
	return 0, io.ErrClosedPipe
}
