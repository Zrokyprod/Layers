// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package redact

import (
	"strings"
	"testing"
)

func TestBodyPreservesUUIDWhileRedactingAdjacentPII(t *testing.T) {
	id := "12345678-1234-1234-1234-123456789012"
	masked := string(Body([]byte(`{"call_id":"` + id + `","message":"run ` + id + ` belongs to user@example.com"}`)))

	if strings.Count(masked, id) != 2 {
		t.Fatalf("UUID was changed: %s", masked)
	}
	if strings.Contains(masked, "user@example.com") {
		t.Fatalf("email was not redacted: %s", masked)
	}
}

func TestBodyRedactsOpaqueTokensWithoutHidingUsageCounts(t *testing.T) {
	masked := string(Body([]byte(`{"access_token":"opaque-access-value","refresh_token":"opaque-refresh-value","prompt_tokens":42}`)))

	if strings.Contains(masked, "opaque-access-value") || strings.Contains(masked, "opaque-refresh-value") {
		t.Fatalf("token was not redacted: %s", masked)
	}
	if !strings.Contains(masked, `"prompt_tokens":42`) {
		t.Fatalf("usage count was changed: %s", masked)
	}
}
