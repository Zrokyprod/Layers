// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

// Package redact strips PII from request/response bodies before logging.
package redact

import (
	"regexp"
	"strings"
)

var patterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*`),
	regexp.MustCompile(`(?i)"api[_-]?key"\s*:\s*"[^"]{6,}"`),
	regexp.MustCompile(`(?i)"authorization"\s*:\s*"[^"]+"`),
	regexp.MustCompile(`\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b`),
	regexp.MustCompile(`\b\d{13,19}\b`), // credit-card-like digit runs
	regexp.MustCompile(`(?i)"password"\s*:\s*"[^"]+"`),
	regexp.MustCompile(`(?i)"secret"\s*:\s*"[^"]+"`),
	regexp.MustCompile(`(?i)"token"\s*:\s*"[^"]+"`),
}

const redacted = "[REDACTED]"

// Body returns a copy of body with PII patterns replaced.
func Body(body []byte) []byte {
	s := string(body)
	for _, re := range patterns {
		s = re.ReplaceAllStringFunc(s, func(match string) string {
			// Keep the JSON key, redact the value only.
			if idx := strings.Index(match, ":"); idx != -1 {
				return match[:idx+1] + ` "` + redacted + `"`
			}
			return redacted
		})
	}
	return []byte(s)
}

// Header returns the header value with auth tokens masked.
func Header(key, value string) string {
	k := strings.ToLower(key)
	if k == "authorization" || k == "x-api-key" || k == "api-key" {
		if len(value) > 8 {
			return value[:4] + "..." + value[len(value)-4:]
		}
		return redacted
	}
	return value
}
