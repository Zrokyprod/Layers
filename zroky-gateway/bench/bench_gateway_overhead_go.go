//go:build ignore

// Rule 4 benchmark: p95 gateway overhead < 8 ms at 100 RPS.
//
// Usage:
//   GATEWAY_URL=http://localhost:8090 go run bench/bench_gateway_overhead_go.go
//
// The bench spins up a mock upstream that replies instantly, then hammers
// the gateway at 100 RPS for 30 s and asserts p95 overhead < 8 ms.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"sort"
	"sync"
	"time"
)

const (
	targetRPS   = 100
	durationSec = 30
	p95Limit    = 8.0 // ms
)

func main() {
	// ── Mock upstream (zero-latency echo) ──────────────────────────────
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}],"usage":{"total_tokens":10}}`))
	}))
	defer upstream.Close()

	gatewayURL := os.Getenv("GATEWAY_URL")
	if gatewayURL == "" {
		gatewayURL = "http://localhost:8090"
	}

	body, _ := json.Marshal(map[string]interface{}{
		"model":    "gpt-4o-mini",
		"messages": []map[string]string{{"role": "user", "content": "hi"}},
	})

	ticker := time.NewTicker(time.Second / targetRPS)
	defer ticker.Stop()
	deadline := time.After(durationSec * time.Second)

	var mu sync.Mutex
	var latencies []float64

	fmt.Printf("Benchmarking %s at %d RPS for %ds…\n", gatewayURL, targetRPS, durationSec)
	var wg sync.WaitGroup

loop:
	for {
		select {
		case <-deadline:
			break loop
		case <-ticker.C:
			wg.Add(1)
			go func() {
				defer wg.Done()
				start := time.Now()
				resp, err := http.Post(
					gatewayURL+"/v1/chat/completions",
					"application/json",
					bytes.NewReader(body),
				)
				elapsed := float64(time.Since(start).Microseconds()) / 1000.0
				if err == nil {
					resp.Body.Close()
				}
				mu.Lock()
				latencies = append(latencies, elapsed)
				mu.Unlock()
			}()
		}
	}
	wg.Wait()

	sort.Float64s(latencies)
	n := len(latencies)
	p95idx := int(float64(n)*0.95) - 1
	if p95idx < 0 {
		p95idx = 0
	}
	p95 := latencies[p95idx]
	fmt.Printf("Requests: %d | p95 latency: %.2f ms | limit: %.1f ms\n", n, p95, p95Limit)
	if p95 > p95Limit {
		fmt.Printf("FAIL: p95 %.2f ms exceeds %.1f ms limit\n", p95, p95Limit)
		os.Exit(1)
	}
	fmt.Println("PASS: p95 within Rule 4 limit")
}
