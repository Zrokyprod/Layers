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

	level, err := zerolog.ParseLevel(cfg.LogLevel)
	if err != nil {
		level = zerolog.InfoLevel
	}
	zerolog.SetGlobalLevel(level)
	if cfg.PrettyLogs {
		log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stdout})
	}

	emitMode, err := emit.ParseMode(cfg.EmitMode)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid emit mode")
	}

	var rdb *redis.Client
	if emitMode.UsesRedis() {
		opts, redisErr := redis.ParseURL(cfg.RedisURL)
		if redisErr != nil {
			log.Fatal().Err(redisErr).Msg("invalid REDIS_URL")
		}
		rdb = redis.NewClient(opts)
		ctx := context.Background()
		if pingErr := rdb.Ping(ctx).Err(); pingErr != nil {
			log.Warn().Err(pingErr).Msg("Redis ping failed; Redis emit will fail")
		}
	}

	emitter, err := emit.NewWithOptions(emit.Options{
		Mode:        emitMode,
		RedisClient: rdb,
		RedisStream: cfg.RedisStream,
		IngestURL:   cfg.ZrokyIngestURL,
		APIKey:      cfg.ZrokyAPIKey,
	})
	if err != nil {
		log.Fatal().Err(err).Msg("failed to configure emitter")
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})

	openAI := proxy.OpenAI
	openAI.BaseURL = cfg.OpenAIBaseURL
	anthropic := proxy.Anthropic
	anthropic.BaseURL = cfg.AnthropicBaseURL
	google := proxy.Google
	google.BaseURL = cfg.GoogleBaseURL

	for _, route := range []struct {
		path     string
		callType string
		apiKey   string
	}{
		{"/v1/chat/completions", "chat", cfg.OpenAIAPIKey},
		{"/v1/responses", "response", cfg.OpenAIAPIKey},
		{"/v1/embeddings", "embedding", cfg.OpenAIAPIKey},
	} {
		mux.Handle(route.path, proxy.HandlerWithOptions(openAI, route.callType, emitter, proxy.Options{
			MaxBodyBytes:         cfg.MaxBodyBytes,
			GatewayAuthToken:     cfg.GatewayAuthToken,
			AllowedProjectIDs:    cfg.AllowedProjectIDs,
			UpstreamAPIKey:       route.apiKey,
			DefaultWorkflowName:  cfg.WorkflowName,
			DefaultPromptVersion: cfg.PromptVersion,
		}, log.Logger))
	}

	mux.Handle("/v1/messages", proxy.HandlerWithOptions(anthropic, "chat", emitter, proxy.Options{
		MaxBodyBytes:         cfg.MaxBodyBytes,
		GatewayAuthToken:     cfg.GatewayAuthToken,
		AllowedProjectIDs:    cfg.AllowedProjectIDs,
		UpstreamAPIKey:       cfg.AnthropicAPIKey,
		DefaultWorkflowName:  cfg.WorkflowName,
		DefaultPromptVersion: cfg.PromptVersion,
	}, log.Logger))
	mux.Handle("/v1beta/models/", proxy.HandlerWithOptions(google, "chat", emitter, proxy.Options{
		MaxBodyBytes:         cfg.MaxBodyBytes,
		GatewayAuthToken:     cfg.GatewayAuthToken,
		AllowedProjectIDs:    cfg.AllowedProjectIDs,
		UpstreamAPIKey:       cfg.GoogleAPIKey,
		DefaultWorkflowName:  cfg.WorkflowName,
		DefaultPromptVersion: cfg.PromptVersion,
	}, log.Logger))

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      mux,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		IdleTimeout:  cfg.IdleTimeout,
	}

	go func() {
		log.Info().Str("port", cfg.Port).Str("emit_mode", string(emitMode)).Msg("zroky-gateway starting")
		if serveErr := srv.ListenAndServe(); serveErr != nil && serveErr != http.ErrServerClosed {
			log.Fatal().Err(serveErr).Msg("server error")
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Info().Msg("shutting down")

	shutCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutCtx)
	if rdb != nil {
		_ = rdb.Close()
	}
	log.Info().Msg("bye")
}
