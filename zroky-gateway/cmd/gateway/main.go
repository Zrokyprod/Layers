// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/zroky-ai/zroky-gateway/internal/config"
	"github.com/zroky-ai/zroky-gateway/internal/emit"
	"github.com/zroky-ai/zroky-gateway/internal/proxy"
)

func main() {
	cfg := config.Load()

	// ── Logger ────────────────────────────────────────────────────────────
	level, err := zerolog.ParseLevel(cfg.LogLevel)
	if err != nil {
		level = zerolog.InfoLevel
	}
	zerolog.SetGlobalLevel(level)
	if cfg.PrettyLogs {
		log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stdout})
	}

	// ── Redis ─────────────────────────────────────────────────────────────
	opts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid REDIS_URL")
	}
	rdb := redis.NewClient(opts)
	ctx := context.Background()
	if pingErr := rdb.Ping(ctx).Err(); pingErr != nil {
		log.Warn().Err(pingErr).Msg("Redis ping failed — emit will fail silently")
	}
	emitter := emit.New(rdb, cfg.RedisStream)

	// ── Routes ────────────────────────────────────────────────────────────
	mux := http.NewServeMux()

	// Health
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})

	// OpenAI-shape routes
	for _, route := range []struct {
		path     string
		callType string
	}{
		{"/v1/chat/completions", "chat"},
		{"/v1/responses", "response"},
		{"/v1/embeddings", "embedding"},
	} {
		mux.Handle(route.path, proxy.Handler(proxy.OpenAI, route.callType, emitter, cfg.MaxBodyBytes, log.Logger))
	}

	// Anthropic-shape route
	mux.Handle("/v1/messages", proxy.Handler(proxy.Anthropic, "chat", emitter, cfg.MaxBodyBytes, log.Logger))

	// Google-shape route (Gemini generateContent)
	mux.Handle("/v1beta/models/", proxy.Handler(proxy.Google, "chat", emitter, cfg.MaxBodyBytes, log.Logger))

	// ── Server ────────────────────────────────────────────────────────────
	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      mux,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		IdleTimeout:  cfg.IdleTimeout,
	}

	go func() {
		log.Info().Str("port", cfg.Port).Msg("zroky-gateway starting")
		if serveErr := srv.ListenAndServe(); serveErr != nil && serveErr != http.ErrServerClosed {
			log.Fatal().Err(serveErr).Msg("server error")
		}
	}()

	// ── Graceful shutdown ─────────────────────────────────────────────────
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Info().Msg("shutting down")

	shutCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutCtx)
	_ = rdb.Close()
	log.Info().Msg("bye")
}
