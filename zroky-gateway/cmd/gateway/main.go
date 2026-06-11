// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package main

import (
	"context"
	"encoding/json"
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
	"github.com/zroky-ai/zroky-gateway/internal/heartbeat"
	"github.com/zroky-ai/zroky-gateway/internal/proxy"
	"github.com/zroky-ai/zroky-gateway/internal/spool"
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

	captureSpool, err := spool.New(spool.Options{
		Dir:                cfg.SpoolDir,
		MaxBytes:           cfg.SpoolMaxBytes,
		HighWatermarkRatio: cfg.SpoolHighWatermark,
		Logger:             log.Logger,
	})
	if err != nil {
		log.Fatal().Err(err).Msg("failed to configure capture spool")
	}
	spoolCtx, stopSpool := context.WithCancel(context.Background())
	defer stopSpool()
	go captureSpool.FlushLoop(spoolCtx, emitter, cfg.SpoolFlushInterval)
	go heartbeat.Loop(spoolCtx, heartbeat.Options{
		URL:            cfg.ZrokyHeartbeatURL,
		APIKey:         cfg.ZrokyAPIKey,
		ProjectID:      heartbeatProjectID(cfg.AllowedProjectIDs),
		GatewayID:      cfg.GatewayID,
		EmitMode:       string(emitMode),
		DurabilityMode: cfg.CaptureDurability,
		Version:        "zroky-gateway",
		Interval:       cfg.HeartbeatInterval,
		StatusFunc:     captureSpool.Status,
		Logger:         log.Logger,
	})

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "ok",
			"spool":  captureSpool.Status(),
		})
	})
	mux.HandleFunc("/ready", func(w http.ResponseWriter, _ *http.Request) {
		status := captureSpool.Status()
		ready := true
		if cfg.CaptureDurability == "fail_closed" {
			ready = captureSpool.CanAccept(cfg.SpoolReserveBytes) == nil
		}
		w.Header().Set("Content-Type", "application/json")
		if !ready {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"ready":  ready,
			"status": status.CaptureStatus,
			"spool":  status,
		})
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
			CaptureSpool:         captureSpool,
			CaptureDurability:    cfg.CaptureDurability,
			SpoolReserveBytes:    cfg.SpoolReserveBytes,
		}, log.Logger))
	}

	mux.Handle("/v1/messages", proxy.HandlerWithOptions(anthropic, "chat", emitter, proxy.Options{
		MaxBodyBytes:         cfg.MaxBodyBytes,
		GatewayAuthToken:     cfg.GatewayAuthToken,
		AllowedProjectIDs:    cfg.AllowedProjectIDs,
		UpstreamAPIKey:       cfg.AnthropicAPIKey,
		DefaultWorkflowName:  cfg.WorkflowName,
		DefaultPromptVersion: cfg.PromptVersion,
		CaptureSpool:         captureSpool,
		CaptureDurability:    cfg.CaptureDurability,
		SpoolReserveBytes:    cfg.SpoolReserveBytes,
	}, log.Logger))
	mux.Handle("/v1beta/models/", proxy.HandlerWithOptions(google, "chat", emitter, proxy.Options{
		MaxBodyBytes:         cfg.MaxBodyBytes,
		GatewayAuthToken:     cfg.GatewayAuthToken,
		AllowedProjectIDs:    cfg.AllowedProjectIDs,
		UpstreamAPIKey:       cfg.GoogleAPIKey,
		DefaultWorkflowName:  cfg.WorkflowName,
		DefaultPromptVersion: cfg.PromptVersion,
		CaptureSpool:         captureSpool,
		CaptureDurability:    cfg.CaptureDurability,
		SpoolReserveBytes:    cfg.SpoolReserveBytes,
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

func heartbeatProjectID(allowed map[string]struct{}) string {
	if len(allowed) != 1 {
		return ""
	}
	for projectID := range allowed {
		return projectID
	}
	return ""
}
