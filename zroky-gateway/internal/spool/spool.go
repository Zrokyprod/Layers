// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

package spool

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync/atomic"
	"time"

	"github.com/rs/zerolog"
	"github.com/zroky-ai/zroky-gateway/internal/emit"
)

type Options struct {
	Dir      string
	MaxBytes int64
	Logger   zerolog.Logger
}

type Status struct {
	Enabled          bool    `json:"enabled"`
	Backlog          int     `json:"backlog"`
	Bytes            int64   `json:"bytes"`
	OldestAgeSeconds float64 `json:"oldest_age_seconds"`
}

type Spool struct {
	dir      string
	maxBytes int64
	logger   zerolog.Logger
	seq      atomic.Uint64
}

type record struct {
	QueuedAt time.Time           `json:"queued_at"`
	Event    *emit.IngestEventV2 `json:"event"`
}

func New(opts Options) (*Spool, error) {
	dir := opts.Dir
	if dir == "" {
		dir = ".zroky-spool"
	}
	maxBytes := opts.MaxBytes
	if maxBytes <= 0 {
		maxBytes = 100 * 1024 * 1024
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	return &Spool{dir: dir, maxBytes: maxBytes, logger: opts.Logger}, nil
}

func (s *Spool) Enqueue(ev *emit.IngestEventV2) error {
	if ev == nil {
		return errors.New("nil ingest event")
	}
	payload, err := json.Marshal(record{QueuedAt: time.Now().UTC(), Event: ev})
	if err != nil {
		return err
	}
	if int64(len(payload)) > s.maxBytes {
		return fmt.Errorf("spool event size %d exceeds max bytes %d", len(payload), s.maxBytes)
	}
	name := fmt.Sprintf("%020d-%06d.json", time.Now().UTC().UnixNano(), s.seq.Add(1))
	tmp := filepath.Join(s.dir, name+".tmp")
	final := filepath.Join(s.dir, name)
	if err := os.WriteFile(tmp, payload, 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, final); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return s.trim()
}

func (s *Spool) FlushLoop(ctx context.Context, emitter *emit.Emitter, interval time.Duration) {
	if interval <= 0 {
		interval = 5 * time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if _, err := s.FlushOnce(ctx, emitter); err != nil {
				s.logger.Warn().Err(err).Msg("spool flush failed")
			}
		}
	}
}

func (s *Spool) FlushOnce(ctx context.Context, emitter *emit.Emitter) (int, error) {
	files, err := s.files()
	if err != nil {
		return 0, err
	}
	flushed := 0
	for _, file := range files {
		path := filepath.Join(s.dir, file.Name())
		raw, err := os.ReadFile(path)
		if err != nil {
			return flushed, err
		}
		var rec record
		if err := json.Unmarshal(raw, &rec); err != nil {
			return flushed, err
		}
		if err := emitter.Emit(ctx, rec.Event); err != nil {
			return flushed, err
		}
		if err := os.Remove(path); err != nil {
			return flushed, err
		}
		flushed++
	}
	return flushed, nil
}

func (s *Spool) Status() Status {
	files, err := s.files()
	if err != nil {
		return Status{Enabled: true}
	}
	var total int64
	var oldest time.Time
	for _, file := range files {
		info, err := file.Info()
		if err != nil {
			continue
		}
		total += info.Size()
		if oldest.IsZero() || info.ModTime().Before(oldest) {
			oldest = info.ModTime()
		}
	}
	var oldestAge float64
	if !oldest.IsZero() {
		oldestAge = time.Since(oldest).Seconds()
	}
	return Status{
		Enabled:          true,
		Backlog:          len(files),
		Bytes:            total,
		OldestAgeSeconds: oldestAge,
	}
}

func (s *Spool) files() ([]os.DirEntry, error) {
	entries, err := os.ReadDir(s.dir)
	if err != nil {
		return nil, err
	}
	files := make([]os.DirEntry, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		files = append(files, entry)
	}
	sort.Slice(files, func(i, j int) bool {
		return files[i].Name() < files[j].Name()
	})
	return files, nil
}

func (s *Spool) trim() error {
	files, err := s.files()
	if err != nil {
		return err
	}
	var total int64
	sizes := make(map[string]int64, len(files))
	for _, file := range files {
		info, err := file.Info()
		if err != nil {
			continue
		}
		sizes[file.Name()] = info.Size()
		total += info.Size()
	}
	for total > s.maxBytes && len(files) > 0 {
		file := files[0]
		files = files[1:]
		path := filepath.Join(s.dir, file.Name())
		if err := os.Remove(path); err != nil {
			return err
		}
		total -= sizes[file.Name()]
	}
	return nil
}
