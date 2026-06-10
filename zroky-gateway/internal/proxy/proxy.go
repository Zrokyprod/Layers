// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

// Package proxy implements the bytes-passthrough reverse proxy core.
// It reads the full request body (up to MaxBodyBytes), forwards it to the
// upstream provider, streams the response back, then emits an IngestEventV2.
package proxy

import (
	"bufio"
	"bytes"
	"context"
	"crypto/subtle"
	"encoding/json"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"github.com/zroky-ai/zroky-gateway/internal/emit"
	"github.com/zroky-ai/zroky-gateway/internal/redact"
)

type captureHeaders struct {
	ProjectID      string
	CallID         string
	AgentName      string
	PromptVersion  string
	SessionID      string
	WorkflowID     string
	WorkflowName   string
	AgentFramework string
	TraceID        string
	ParentCallID   string
	StepIndex      *int
	CodeSHA        string
	DeploymentID   string
	ModelVersion   string
	ToolSchemaVer  string
	RAGVersion     string
	SpanType       string
	SpanName       string
}

// Provider describes an upstream LLM endpoint.
type Provider struct {
	Name    string // "openai" | "anthropic" | "google"
	BaseURL string
	// HeaderKey is the auth header name the provider expects.
	HeaderKey string
}

type Options struct {
	MaxBodyBytes         int64
	GatewayAuthToken     string
	AllowedProjectIDs    map[string]struct{}
	UpstreamAPIKey       string
	DefaultWorkflowName  string
	DefaultPromptVersion string
	CaptureSpool         CaptureSpooler
}

type CaptureSpooler interface {
	Enqueue(ev *emit.IngestEventV2) error
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
	return HandlerWithOptions(provider, callType, emitter, Options{MaxBodyBytes: maxBodyBytes}, logger)
}

func HandlerWithOptions(
	provider Provider,
	callType string,
	emitter *emit.Emitter,
	opts Options,
	logger zerolog.Logger,
) http.HandlerFunc {
	hc := &http.Client{Timeout: 120 * time.Second}
	maxBodyBytes := opts.MaxBodyBytes

	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		if !authorizedGatewayRequest(r.Header, opts.GatewayAuthToken) {
			http.Error(w, "missing or invalid gateway auth token", http.StatusUnauthorized)
			return
		}

		// ── 1. Read request body ─────────────────────────────────────────
		reqBody, tooLarge, err := readBoundedBody(r.Body, maxBodyBytes)
		if err != nil {
			http.Error(w, "failed to read request body", http.StatusBadRequest)
			return
		}
		if tooLarge {
			http.Error(w, "request body exceeds MAX_BODY_BYTES", http.StatusRequestEntityTooLarge)
			return
		}

		// ── 2. Extract tenant / project ID from header ───────────────────
		capture := readCaptureHeaders(r.Header)
		if capture.WorkflowName == "" {
			capture.WorkflowName = opts.DefaultWorkflowName
		}
		if capture.PromptVersion == "" {
			capture.PromptVersion = opts.DefaultPromptVersion
		}
		if strings.TrimSpace(capture.ProjectID) == "" {
			http.Error(w, "missing X-Zroky-Project-Id", http.StatusBadRequest)
			return
		}

		// ── 3. Extract upstream API key via Zroky key-fetch ─────────────
		if !allowedProject(capture.ProjectID, opts.AllowedProjectIDs) {
			http.Error(w, "project is not allowed for this gateway", http.StatusForbidden)
			return
		}

		upstreamKey := providerAuthValue(provider, opts.UpstreamAPIKey)
		if upstreamKey == "" {
			upstreamKey = r.Header.Get(provider.HeaderKey)
		}
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
			respBody, err = copyAndCapture(w, resp.Body, maxBodyBytes)
			if err != nil {
				status = "error"
				errMsg = "response stream interrupted"
			}
		}

		// ── 5. Emit IngestEventV2 (best-effort, never blocks) ────────────
		go func() {
			ev := buildEvent(
				capture, provider, callType,
				latencyMS, statusCode, status, errMsg,
				reqBody, respBody,
			)
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			if emitErr := emitter.Emit(ctx, ev); emitErr != nil {
				if opts.CaptureSpool != nil {
					if spoolErr := opts.CaptureSpool.Enqueue(ev); spoolErr != nil {
						logger.Error().Err(emitErr).Err(spoolErr).Msg("emit failed and spool enqueue failed")
						return
					}
					logger.Warn().Err(emitErr).Msg("emit failed; event spooled")
					return
				}
				logger.Warn().Err(emitErr).Msg("emit failed")
			}
		}()

		logger.Info().
			Str("provider", provider.Name).
			Str("call_type", callType).
			Int("status", statusCode).
			Float64("latency_ms", latencyMS).
			Str("project_id", capture.ProjectID).
			Msg("proxied")
	}
}

// ── helpers ───────────────────────────────────────────────────────────────────

func readBoundedBody(body io.Reader, maxBytes int64) ([]byte, bool, error) {
	if maxBytes <= 0 {
		out, err := io.ReadAll(body)
		return out, false, err
	}

	out, err := io.ReadAll(io.LimitReader(body, maxBytes+1))
	if err != nil {
		return nil, false, err
	}
	if int64(len(out)) > maxBytes {
		return nil, true, nil
	}
	return out, false, nil
}

func copyAndCapture(dst io.Writer, src io.Reader, maxCaptureBytes int64) ([]byte, error) {
	var captured bytes.Buffer
	buf := make([]byte, 32*1024)
	flusher, _ := dst.(http.Flusher)

	for {
		n, readErr := src.Read(buf)
		if n > 0 {
			chunk := buf[:n]
			if maxCaptureBytes > 0 && int64(captured.Len()) < maxCaptureBytes {
				remaining := int(maxCaptureBytes - int64(captured.Len()))
				if remaining > len(chunk) {
					remaining = len(chunk)
				}
				_, _ = captured.Write(chunk[:remaining])
			}
			if _, writeErr := dst.Write(chunk); writeErr != nil {
				return captured.Bytes(), writeErr
			}
			if flusher != nil {
				flusher.Flush()
			}
		}
		if readErr == io.EOF {
			return captured.Bytes(), nil
		}
		if readErr != nil {
			return captured.Bytes(), readErr
		}
	}
}

func copyHeaders(src, dst http.Header, authKey, upstreamKey string) {
	for k, vs := range src {
		if isZrokyInternalHeader(k) {
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

func isZrokyInternalHeader(key string) bool {
	normalized := strings.ToLower(key)
	return strings.HasPrefix(normalized, "x-zroky-") || normalized == "x-project-id"
}

func authorizedGatewayRequest(headers http.Header, expectedToken string) bool {
	expectedToken = strings.TrimSpace(expectedToken)
	if expectedToken == "" {
		return true
	}
	for _, candidate := range []string{
		headers.Get("X-Zroky-Gateway-Token"),
		headers.Get("X-Zroky-Gateway-Key"),
		bearerToken(headers.Get("Authorization")),
	} {
		candidate = strings.TrimSpace(candidate)
		if candidate != "" && subtle.ConstantTimeCompare([]byte(candidate), []byte(expectedToken)) == 1 {
			return true
		}
	}
	return false
}

func bearerToken(header string) string {
	value := strings.TrimSpace(header)
	if len(value) >= 7 && strings.EqualFold(value[:7], "bearer ") {
		return strings.TrimSpace(value[7:])
	}
	return ""
}

func allowedProject(projectID string, allowed map[string]struct{}) bool {
	if len(allowed) == 0 {
		return true
	}
	_, ok := allowed[strings.TrimSpace(projectID)]
	return ok
}

func providerAuthValue(provider Provider, apiKey string) string {
	apiKey = strings.TrimSpace(apiKey)
	if apiKey == "" {
		return ""
	}
	if strings.EqualFold(provider.HeaderKey, "Authorization") && !strings.HasPrefix(strings.ToLower(apiKey), "bearer ") {
		return "Bearer " + apiKey
	}
	return apiKey
}

func readCaptureHeaders(headers http.Header) captureHeaders {
	var stepIndex *int
	if rawStep := headers.Get("X-Zroky-Step-Index"); rawStep != "" {
		if parsed, err := strconv.Atoi(rawStep); err == nil && parsed >= 0 {
			stepIndex = &parsed
		}
	}

	return captureHeaders{
		ProjectID:      firstHeader(headers, "X-Zroky-Project-Id", "X-Project-Id"),
		CallID:         headers.Get("X-Zroky-Call-Id"),
		AgentName:      headers.Get("X-Zroky-Agent-Name"),
		PromptVersion:  headers.Get("X-Zroky-Prompt-Version"),
		SessionID:      headers.Get("X-Zroky-Session-Id"),
		WorkflowID:     headers.Get("X-Zroky-Workflow-Id"),
		WorkflowName:   headers.Get("X-Zroky-Workflow-Name"),
		AgentFramework: headers.Get("X-Zroky-Agent-Framework"),
		TraceID:        headers.Get("X-Zroky-Trace-Id"),
		ParentCallID:   headers.Get("X-Zroky-Parent-Call-Id"),
		StepIndex:      stepIndex,
		CodeSHA:        headers.Get("X-Zroky-Code-Sha"),
		DeploymentID:   headers.Get("X-Zroky-Deployment-Id"),
		ModelVersion:   headers.Get("X-Zroky-Model-Version"),
		ToolSchemaVer:  headers.Get("X-Zroky-Tool-Schema-Version"),
		RAGVersion:     headers.Get("X-Zroky-Rag-Version"),
		SpanType:       headers.Get("X-Zroky-Span-Type"),
		SpanName:       headers.Get("X-Zroky-Span-Name"),
	}
}

func firstHeader(headers http.Header, keys ...string) string {
	for _, key := range keys {
		if value := strings.TrimSpace(headers.Get(key)); value != "" {
			return value
		}
	}
	return ""
}

func buildEvent(
	capture captureHeaders, provider Provider, callType string,
	latencyMS float64, statusCode int, status, errMsg string,
	reqBody, respBody []byte,
) *emit.IngestEventV2 {
	model := extractModel(reqBody)
	var reqMap, respMap map[string]interface{}
	_ = json.Unmarshal(redact.Body(reqBody), &reqMap)
	respMap = decodeResponseBody(respBody)

	usage := extractUsage(respMap)
	toolCalls := responseToolCalls(respMap)
	output := outputContent(respMap)
	versions := versionMap(capture, model)
	spanType := strings.TrimSpace(capture.SpanType)
	if spanType == "" {
		spanType = "llm_call"
	}
	spanName := strings.TrimSpace(capture.SpanName)
	if spanName == "" {
		spanName = provider.Name + "/" + model
	}
	input := map[string]interface{}{"request": reqMap}
	if messages, ok := reqMap["messages"]; ok {
		input["messages"] = messages
	}

	return &emit.IngestEventV2{
		SchemaVersion:    "v2",
		CallID:           capture.CallID,
		ProjectID:        capture.ProjectID,
		RequestID:        extractResponseID(respMap),
		Provider:         provider.Name,
		Model:            model,
		CallType:         callType,
		LatencyMS:        latencyMS,
		PromptTokens:     usage.prompt,
		CompletionTokens: usage.completion,
		OutputTokens:     usage.completion,
		TotalTokens:      usage.total,
		Status:           status,
		StatusCode:       statusCode,
		AgentName:        capture.AgentName,
		PromptVersion:    capture.PromptVersion,
		SessionID:        capture.SessionID,
		WorkflowID:       capture.WorkflowID,
		WorkflowName:     capture.WorkflowName,
		StepIndex:        capture.StepIndex,
		AgentFramework:   capture.AgentFramework,
		TraceID:          capture.TraceID,
		ParentCallID:     capture.ParentCallID,
		SpanType:         spanType,
		SpanName:         spanName,
		SpanIndex:        capture.StepIndex,
		Input:            input,
		SystemPrompt:     messageContent(reqMap, "system"),
		UserInput:        messageContent(reqMap, "user"),
		FinalAnswer:      output,
		Versions:         versions,
		CaptureSource:    "gateway_http_direct",
		MaskingVersion:   "gateway-redact-v1",
		PiiMasked:        true,
		RequestBody:      reqMap,
		ResponseBody:     respMap,
		ToolDefinitions:  listOfMaps(reqMap["tools"]),
		ToolCalls:        toolCalls,
		ToolCallsMade:    toolCalls,
		OutputContent:    output,
		FinishReason:     finishReason(respMap),
		StopReason:       stopReason(respMap),
		Metadata: map[string]interface{}{
			"source":      "gateway_http_direct",
			"status_code": statusCode,
		},
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

func extractResponseID(resp map[string]interface{}) string {
	if resp == nil {
		return ""
	}
	if v, ok := resp["id"].(string); ok {
		return v
	}
	return ""
}

func outputContent(resp map[string]interface{}) string {
	choices, ok := resp["choices"].([]interface{})
	if !ok || len(choices) == 0 {
		return ""
	}
	first, ok := choices[0].(map[string]interface{})
	if !ok {
		return ""
	}
	message, ok := first["message"].(map[string]interface{})
	if !ok {
		return ""
	}
	content, _ := message["content"].(string)
	return content
}

func messageContent(req map[string]interface{}, role string) string {
	messages, ok := req["messages"].([]interface{})
	if !ok {
		return ""
	}
	for i := len(messages) - 1; i >= 0; i-- {
		message, ok := messages[i].(map[string]interface{})
		if !ok {
			continue
		}
		if messageRole, _ := message["role"].(string); messageRole != role {
			continue
		}
		if content, _ := message["content"].(string); content != "" {
			if len(content) > 12000 {
				return content[:12000]
			}
			return content
		}
	}
	return ""
}

func versionMap(capture captureHeaders, model string) map[string]interface{} {
	values := map[string]interface{}{
		"code_sha":            strings.TrimSpace(capture.CodeSHA),
		"deployment_id":       strings.TrimSpace(capture.DeploymentID),
		"model_version":       firstNonEmpty(strings.TrimSpace(capture.ModelVersion), model),
		"tool_schema_version": strings.TrimSpace(capture.ToolSchemaVer),
		"rag_version":         strings.TrimSpace(capture.RAGVersion),
		"prompt_version":      strings.TrimSpace(capture.PromptVersion),
	}
	out := map[string]interface{}{}
	for key, value := range values {
		if text, ok := value.(string); ok && strings.TrimSpace(text) != "" {
			out[key] = text
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func responseToolCalls(resp map[string]interface{}) []map[string]interface{} {
	choices, ok := resp["choices"].([]interface{})
	if !ok || len(choices) == 0 {
		return nil
	}
	first, ok := choices[0].(map[string]interface{})
	if !ok {
		return nil
	}
	message, ok := first["message"].(map[string]interface{})
	if !ok {
		return nil
	}
	return listOfMaps(message["tool_calls"])
}

func finishReason(resp map[string]interface{}) string {
	if resp == nil {
		return ""
	}
	if value := stringFromMap(resp, "finish_reason"); value != "" {
		return value
	}
	choices, ok := resp["choices"].([]interface{})
	if !ok || len(choices) == 0 {
		return ""
	}
	first, ok := choices[0].(map[string]interface{})
	if !ok {
		return ""
	}
	return stringFromMap(first, "finish_reason")
}

func stopReason(resp map[string]interface{}) string {
	if resp == nil {
		return ""
	}
	if value := stringFromMap(resp, "stop_reason"); value != "" {
		return value
	}
	if value := finishReason(resp); value != "" {
		return value
	}
	return ""
}

func listOfMaps(value interface{}) []map[string]interface{} {
	items, ok := value.([]interface{})
	if !ok {
		return nil
	}
	out := make([]map[string]interface{}, 0, len(items))
	for _, item := range items {
		if row, ok := item.(map[string]interface{}); ok {
			out = append(out, row)
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func decodeResponseBody(body []byte) map[string]interface{} {
	if len(body) == 0 {
		return nil
	}

	redactedBody := redact.Body(body)
	var resp map[string]interface{}
	if err := json.Unmarshal(redactedBody, &resp); err == nil && resp != nil {
		return resp
	}
	return parseSSEBody(redactedBody)
}

func parseSSEBody(body []byte) map[string]interface{} {
	scanner := bufio.NewScanner(bytes.NewReader(body))
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	acc := &sseAccumulator{
		toolCalls: map[int]map[string]interface{}{},
	}
	dataLines := []string{}

	flushFrame := func() {
		if len(dataLines) == 0 {
			return
		}
		frameLines := append([]string(nil), dataLines...)
		data := strings.TrimSpace(strings.Join(frameLines, "\n"))
		dataLines = dataLines[:0]
		if data == "" || data == "[DONE]" {
			return
		}

		var chunk map[string]interface{}
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			for _, lineData := range frameLines {
				lineData = strings.TrimSpace(lineData)
				if lineData == "" || lineData == "[DONE]" {
					continue
				}
				var lineChunk map[string]interface{}
				if lineErr := json.Unmarshal([]byte(lineData), &lineChunk); lineErr == nil {
					acc.captureChunk(lineChunk)
				}
			}
			return
		}
		acc.captureChunk(chunk)
	}

	for scanner.Scan() {
		line := strings.TrimRight(scanner.Text(), "\r")
		if strings.TrimSpace(line) == "" {
			flushFrame()
			continue
		}
		if strings.HasPrefix(line, ":") {
			continue
		}
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		dataLines = append(dataLines, strings.TrimSpace(strings.TrimPrefix(line, "data:")))
	}
	flushFrame()

	return acc.toResponse()
}

type sseAccumulator struct {
	output       strings.Builder
	responseID   string
	usage        map[string]interface{}
	finishReason string
	stopReason   string
	toolCalls    map[int]map[string]interface{}
	chunks       int
}

func (a *sseAccumulator) captureChunk(chunk map[string]interface{}) {
	a.chunks++
	if a.responseID == "" {
		a.responseID = stringFromMap(chunk, "id")
	}
	a.mergeUsage(chunk["usage"])
	a.captureFinishReasons(chunk)
	a.captureOpenAIChatChunk(chunk)
	a.captureAnthropicChunk(chunk)
	a.captureOpenAIResponsesChunk(chunk)
}

func (a *sseAccumulator) toResponse() map[string]interface{} {
	if a.chunks == 0 {
		return nil
	}

	message := map[string]interface{}{}
	if a.output.Len() > 0 {
		message["content"] = a.output.String()
	}
	if toolCalls := a.sortedToolCalls(); len(toolCalls) > 0 {
		message["tool_calls"] = toolCalls
	}

	choice := map[string]interface{}{"message": message}
	if a.finishReason != "" {
		choice["finish_reason"] = a.finishReason
	}

	resp := map[string]interface{}{
		"stream":          true,
		"chunks_captured": a.chunks,
		"choices": []interface{}{
			choice,
		},
	}
	if a.responseID != "" {
		resp["id"] = a.responseID
	}
	if a.usage != nil {
		resp["usage"] = a.usage
	}
	if a.finishReason != "" {
		resp["finish_reason"] = a.finishReason
	}
	if a.stopReason != "" {
		resp["stop_reason"] = a.stopReason
	}
	return resp
}

func (a *sseAccumulator) captureOpenAIChatChunk(chunk map[string]interface{}) {
	choices, ok := chunk["choices"].([]interface{})
	if !ok || len(choices) == 0 {
		return
	}
	first, ok := choices[0].(map[string]interface{})
	if !ok {
		return
	}
	if finishReason := stringFromMap(first, "finish_reason"); finishReason != "" {
		a.finishReason = finishReason
	}
	if delta, ok := first["delta"].(map[string]interface{}); ok {
		if content := stringFromMap(delta, "content"); content != "" {
			a.output.WriteString(content)
		}
		a.mergeToolCallDeltas(delta["tool_calls"])
	}
	if message, ok := first["message"].(map[string]interface{}); ok {
		if content := stringFromMap(message, "content"); content != "" {
			a.output.WriteString(content)
		}
		a.mergeToolCallDeltas(message["tool_calls"])
	}
}

func (a *sseAccumulator) captureAnthropicChunk(chunk map[string]interface{}) {
	if message, ok := chunk["message"].(map[string]interface{}); ok {
		if a.responseID == "" {
			a.responseID = stringFromMap(message, "id")
		}
		a.mergeUsage(message["usage"])
		if stopReason := stringFromMap(message, "stop_reason"); stopReason != "" {
			a.stopReason = stopReason
		}
	}
	if delta, ok := chunk["delta"].(map[string]interface{}); ok {
		if text := stringFromMap(delta, "text"); text != "" {
			a.output.WriteString(text)
		}
		if stopReason := stringFromMap(delta, "stop_reason"); stopReason != "" {
			a.stopReason = stopReason
		}
	}
}

func (a *sseAccumulator) captureOpenAIResponsesChunk(chunk map[string]interface{}) {
	eventType := stringFromMap(chunk, "type")
	if eventType == "response.output_text.delta" {
		if delta := stringFromMap(chunk, "delta"); delta != "" {
			a.output.WriteString(delta)
		}
	}
	if eventType == "response.output_text.done" && a.output.Len() == 0 {
		if text := stringFromMap(chunk, "text"); text != "" {
			a.output.WriteString(text)
		}
	}

	response, ok := chunk["response"].(map[string]interface{})
	if !ok {
		return
	}
	if a.responseID == "" {
		a.responseID = stringFromMap(response, "id")
	}
	a.mergeUsage(response["usage"])
	a.captureFinishReasons(response)
	if a.output.Len() == 0 {
		a.appendResponseOutput(response)
	}
	if details, ok := response["incomplete_details"].(map[string]interface{}); ok {
		if reason := stringFromMap(details, "reason"); reason != "" {
			a.finishReason = reason
			a.stopReason = reason
		}
	}
}

func (a *sseAccumulator) appendResponseOutput(response map[string]interface{}) {
	outputItems, ok := response["output"].([]interface{})
	if !ok {
		return
	}
	for _, outputItem := range outputItems {
		item, ok := outputItem.(map[string]interface{})
		if !ok {
			continue
		}
		contentItems, ok := item["content"].([]interface{})
		if !ok {
			continue
		}
		for _, contentItem := range contentItems {
			content, ok := contentItem.(map[string]interface{})
			if !ok {
				continue
			}
			if text := stringFromMap(content, "text"); text != "" {
				a.output.WriteString(text)
			}
		}
	}
}

func (a *sseAccumulator) mergeUsage(raw interface{}) {
	usage, ok := raw.(map[string]interface{})
	if !ok || usage == nil {
		return
	}
	if a.usage == nil {
		a.usage = map[string]interface{}{}
	}
	for key, value := range usage {
		if value != nil {
			a.usage[key] = value
		}
	}
}

func (a *sseAccumulator) captureFinishReasons(values map[string]interface{}) {
	if finishReason := stringFromMap(values, "finish_reason"); finishReason != "" {
		a.finishReason = finishReason
	}
	if stopReason := stringFromMap(values, "stop_reason"); stopReason != "" {
		a.stopReason = stopReason
	}
}

func (a *sseAccumulator) mergeToolCallDeltas(raw interface{}) {
	items, ok := raw.([]interface{})
	if !ok {
		return
	}
	for position, item := range items {
		fragment, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		index, ok := intFromValue(fragment["index"])
		if !ok {
			index = position
		}
		toolCall := a.toolCalls[index]
		if toolCall == nil {
			toolCall = map[string]interface{}{}
			a.toolCalls[index] = toolCall
		}
		if id := stringFromMap(fragment, "id"); id != "" {
			toolCall["id"] = id
		}
		if callType := stringFromMap(fragment, "type"); callType != "" {
			toolCall["type"] = callType
		}
		function, ok := fragment["function"].(map[string]interface{})
		if !ok {
			continue
		}
		storedFunction, ok := toolCall["function"].(map[string]interface{})
		if !ok {
			storedFunction = map[string]interface{}{}
			toolCall["function"] = storedFunction
		}
		if name := stringFromMap(function, "name"); name != "" {
			storedFunction["name"] = name
		}
		if arguments := stringFromMap(function, "arguments"); arguments != "" {
			if previous, ok := storedFunction["arguments"].(string); ok {
				storedFunction["arguments"] = previous + arguments
			} else {
				storedFunction["arguments"] = arguments
			}
		}
	}
}

func (a *sseAccumulator) sortedToolCalls() []interface{} {
	if len(a.toolCalls) == 0 {
		return nil
	}
	indexes := make([]int, 0, len(a.toolCalls))
	for index := range a.toolCalls {
		indexes = append(indexes, index)
	}
	sort.Ints(indexes)

	out := make([]interface{}, 0, len(indexes))
	for _, index := range indexes {
		out = append(out, a.toolCalls[index])
	}
	return out
}

func intFromValue(value interface{}) (int, bool) {
	switch v := value.(type) {
	case int:
		return v, true
	case int64:
		return int(v), true
	case float64:
		return int(v), true
	default:
		return 0, false
	}
}

func stringFromMap(values map[string]interface{}, key string) string {
	if value, ok := values[key].(string); ok {
		return value
	}
	return ""
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
