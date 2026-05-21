// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds all gateway configuration resolved from environment variables.
type Config struct {
	Port            string
	ReadTimeout     time.Duration
	WriteTimeout    time.Duration
	IdleTimeout     time.Duration
	RedisURL        string
	RedisStream     string
	ZrokyAPIURL     string
	ZrokyAPIKey     string // gateway-to-control-plane auth
	MaxBodyBytes    int64
	LogLevel        string
	PrettyLogs      bool
}

func Load() *Config {
	return &Config{
		Port:         getenv("PORT", "8090"),
		ReadTimeout:  parseDuration("READ_TIMEOUT", 30*time.Second),
		WriteTimeout: parseDuration("WRITE_TIMEOUT", 60*time.Second),
		IdleTimeout:  parseDuration("IDLE_TIMEOUT", 120*time.Second),
		RedisURL:     getenv("REDIS_URL", "redis://localhost:6379"),
		RedisStream:  getenv("REDIS_STREAM", "zroky:ingest:v2"),
		ZrokyAPIURL:  getenv("ZROKY_API_URL", "https://api.zroky.com"),
		ZrokyAPIKey:  getenv("ZROKY_GATEWAY_API_KEY", ""),
		MaxBodyBytes: parseInt64("MAX_BODY_BYTES", 4*1024*1024), // 4 MB
		LogLevel:     getenv("LOG_LEVEL", "info"),
		PrettyLogs:   getenv("PRETTY_LOGS", "false") == "true",
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
