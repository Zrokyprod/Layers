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
	"sync"
	"sync/atomic"
	"time"

	"github.com/rs/zerolog"
	"github.com/zroky-ai/zroky-gateway/internal/emit"
)

type Options struct {
	Dir                string
	MaxBytes           int64
	HighWatermarkRatio float64
	Logger             zerolog.Logger
}

type Status struct {
	Enabled          bool    `json:"enabled"`
	Backlog          int     `json:"backlog"`
	Bytes            int64   `json:"bytes"`
	MaxBytes         int64   `json:"max_bytes"`
	ReservedBytes    int64   `json:"reserved_bytes"`
	OldestAgeSeconds float64 `json:"oldest_age_seconds"`
	HighWatermark    bool    `json:"high_watermark"`
	CaptureStatus    string  `json:"capture_status"`
	EnqueuedCount    uint64  `json:"enqueued_count"`
	FlushedCount     uint64  `json:"flushed_count"`
	EmitFailures     uint64  `json:"emit_failures"`
	EnqueueFailures  uint64  `json:"enqueue_failures"`
	FlushFailures    uint64  `json:"flush_failures"`
	LossCount        uint64  `json:"loss_count"`
	Backpressure     uint64  `json:"backpressure_rejections"`
	LastError        string  `json:"last_error,omitempty"`
}

type Spool struct {
	dir                string
	maxBytes           int64
	highWatermarkRatio float64
	logger             zerolog.Logger
	seq                atomic.Uint64
	mu                 sync.Mutex
	reservedBytes      int64
	enqueuedCount      atomic.Uint64
	flushedCount       atomic.Uint64
	emitFailures       atomic.Uint64
	enqueueFailures    atomic.Uint64
	flushFailures      atomic.Uint64
	lossCount          atomic.Uint64
	backpressure       atomic.Uint64
	lastError          atomic.Value
}

type record struct {
	QueuedAt      time.Time           `json:"queued_at"`
	Attempts      int                 `json:"attempt_count"`
	LastAttemptAt *time.Time          `json:"last_attempt_at,omitempty"`
	LastError     string              `json:"last_error,omitempty"`
	Event         *emit.IngestEventV2 `json:"event"`
}

type Reservation struct {
	spool    *Spool
	bytes    int64
	released atomic.Bool
}

var ErrSpoolFull = errors.New("capture spool is full")

func New(opts Options) (*Spool, error) {
	dir := opts.Dir
	if dir == "" {
		dir = ".zroky-spool"
	}
	maxBytes := opts.MaxBytes
	if maxBytes <= 0 {
		maxBytes = 100 * 1024 * 1024
	}
	highWatermarkRatio := opts.HighWatermarkRatio
	if highWatermarkRatio <= 0 || highWatermarkRatio > 1 {
		highWatermarkRatio = 0.85
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	return &Spool{dir: dir, maxBytes: maxBytes, highWatermarkRatio: highWatermarkRatio, logger: opts.Logger}, nil
}

func (s *Spool) Enqueue(ev *emit.IngestEventV2) error {
	payload, err := marshalRecord(record{QueuedAt: time.Now().UTC(), Event: ev})
	if err != nil {
		s.RecordLoss(err)
		return err
	}
	reservationHandle, err := s.Reserve(int64(len(payload)))
	if err != nil {
		s.RecordEnqueueFailure(err)
		return err
	}
	reservation, _ := reservationHandle.(*Reservation)
	return s.EnqueueReservedPayload(payload, reservation)
}

func (s *Spool) EnqueueReserved(ev *emit.IngestEventV2, reservation interface{ Release() }) error {
	payload, err := marshalRecord(record{QueuedAt: time.Now().UTC(), Event: ev})
	if err != nil {
		s.RecordLoss(err)
		return err
	}
	if typed, ok := reservation.(*Reservation); ok {
		return s.EnqueueReservedPayload(payload, typed)
	}
	if reservation != nil {
		reservation.Release()
	}
	return s.EnqueueReservedPayload(payload, nil)
}

func (s *Spool) EnqueueReservedPayload(payload []byte, reservation *Reservation) error {
	if int64(len(payload)) > s.maxBytes {
		err := fmt.Errorf("spool event size %d exceeds max bytes %d", len(payload), s.maxBytes)
		s.RecordLoss(err)
		if reservation != nil {
			reservation.Release()
		}
		return err
	}
	if reservation == nil {
		reservationHandle, err := s.Reserve(int64(len(payload)))
		if err != nil {
			s.RecordEnqueueFailure(err)
			return err
		}
		var ok bool
		reservation, ok = reservationHandle.(*Reservation)
		if !ok {
			reservationHandle.Release()
			err := errors.New("invalid spool reservation")
			s.RecordEnqueueFailure(err)
			return err
		}
	}
	defer reservation.Release()

	if extra := int64(len(payload)) - reservation.bytes; extra > 0 {
		if err := s.growReservation(reservation, extra); err != nil {
			s.RecordEnqueueFailure(err)
			return err
		}
	}

	name := fmt.Sprintf("%020d-%06d.json", time.Now().UTC().UnixNano(), s.seq.Add(1))
	tmp := filepath.Join(s.dir, name+".tmp")
	final := filepath.Join(s.dir, name)
	if err := os.WriteFile(tmp, payload, 0o600); err != nil {
		s.RecordEnqueueFailure(err)
		return err
	}
	file, err := os.OpenFile(tmp, os.O_RDONLY, 0)
	if err == nil {
		_ = file.Sync()
		_ = file.Close()
	}
	if err := os.Rename(tmp, final); err != nil {
		_ = os.Remove(tmp)
		s.RecordEnqueueFailure(err)
		return err
	}
	s.enqueuedCount.Add(1)
	return nil
}

func marshalRecord(rec record) ([]byte, error) {
	if rec.Event == nil {
		return nil, errors.New("nil ingest event")
	}
	if rec.QueuedAt.IsZero() {
		rec.QueuedAt = time.Now().UTC()
	}
	return json.Marshal(rec)
}

func (s *Spool) Reserve(bytes int64) (interface{ Release() }, error) {
	if bytes <= 0 {
		bytes = 256 * 1024
	}
	if bytes > s.maxBytes {
		return nil, fmt.Errorf("reservation size %d exceeds max bytes %d", bytes, s.maxBytes)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	used, err := s.currentBytesLocked()
	if err != nil {
		return nil, err
	}
	if used+s.reservedBytes+bytes > s.maxBytes {
		return nil, ErrSpoolFull
	}
	s.reservedBytes += bytes
	return &Reservation{spool: s, bytes: bytes}, nil
}

func (r *Reservation) Release() {
	if r == nil || r.spool == nil || r.released.Swap(true) {
		return
	}
	r.spool.mu.Lock()
	defer r.spool.mu.Unlock()
	r.spool.reservedBytes -= r.bytes
	if r.spool.reservedBytes < 0 {
		r.spool.reservedBytes = 0
	}
}

func (s *Spool) growReservation(reservation *Reservation, extra int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	used, err := s.currentBytesLocked()
	if err != nil {
		return err
	}
	if used+s.reservedBytes+extra > s.maxBytes {
		return ErrSpoolFull
	}
	s.reservedBytes += extra
	reservation.bytes += extra
	return nil
}

func (s *Spool) RecordEmitFailure(err error) {
	s.emitFailures.Add(1)
	s.setLastError(err)
}

func (s *Spool) RecordEnqueueFailure(err error) {
	s.enqueueFailures.Add(1)
	s.setLastError(err)
}

func (s *Spool) RecordFlushFailure(err error) {
	s.flushFailures.Add(1)
	s.setLastError(err)
}

func (s *Spool) RecordLoss(err error) {
	s.lossCount.Add(1)
	s.setLastError(err)
}

func (s *Spool) RecordBackpressure(err error) {
	s.backpressure.Add(1)
	s.setLastError(err)
}

func (s *Spool) setLastError(err error) {
	if err != nil {
		s.lastError.Store(err.Error())
	}
}

func (s *Spool) currentBytesLocked() (int64, error) {
	files, err := s.files()
	if err != nil {
		return 0, err
	}
	var total int64
	for _, file := range files {
		info, err := file.Info()
		if err != nil {
			continue
		}
		total += info.Size()
	}
	return total, nil
}

func (s *Spool) CanAccept(bytes int64) error {
	reservation, err := s.Reserve(bytes)
	if err != nil {
		return err
	}
	reservation.Release()
	return nil
}

func (s *Spool) legacyEnqueue(ev *emit.IngestEventV2) error {
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
	return nil
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
			s.RecordLoss(err)
			_ = os.Rename(path, path+".bad")
			continue
		}
		now := time.Now().UTC()
		rec.Attempts++
		rec.LastAttemptAt = &now
		if err := emitter.Emit(ctx, rec.Event); err != nil {
			rec.LastError = err.Error()
			if updated, marshalErr := json.Marshal(rec); marshalErr == nil {
				_ = os.WriteFile(path, updated, 0o600)
			}
			s.RecordFlushFailure(err)
			return flushed, err
		}
		if err := os.Remove(path); err != nil {
			return flushed, err
		}
		s.flushedCount.Add(1)
		flushed++
	}
	return flushed, nil
}

func (s *Spool) Status() Status {
	s.mu.Lock()
	reserved := s.reservedBytes
	s.mu.Unlock()
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
	highWatermark := total+reserved >= int64(float64(s.maxBytes)*s.highWatermarkRatio)
	status := "ok"
	if s.lossCount.Load() > 0 {
		status = "loss_detected"
	} else if s.backpressure.Load() > 0 || highWatermark {
		status = "backpressure"
	} else if len(files) > 0 || s.emitFailures.Load() > 0 || s.flushFailures.Load() > 0 || s.enqueueFailures.Load() > 0 {
		status = "degraded"
	}
	lastError := ""
	if raw := s.lastError.Load(); raw != nil {
		lastError, _ = raw.(string)
	}
	return Status{
		Enabled:          true,
		Backlog:          len(files),
		Bytes:            total,
		MaxBytes:         s.maxBytes,
		ReservedBytes:    reserved,
		OldestAgeSeconds: oldestAge,
		HighWatermark:    highWatermark,
		CaptureStatus:    status,
		EnqueuedCount:    s.enqueuedCount.Load(),
		FlushedCount:     s.flushedCount.Load(),
		EmitFailures:     s.emitFailures.Load(),
		EnqueueFailures:  s.enqueueFailures.Load(),
		FlushFailures:    s.flushFailures.Load(),
		LossCount:        s.lossCount.Load(),
		Backpressure:     s.backpressure.Load(),
		LastError:        lastError,
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
