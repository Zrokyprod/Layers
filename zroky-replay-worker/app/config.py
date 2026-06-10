# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    CONTROL_PLANE_URL: str = "https://api.zroky.com"
    WORKER_TOKEN: str = ""
    WORKER_ID: str = ""
    ARTIFACT_SIGNING_KEY: str = ""
    ARTIFACT_SIGNATURE_REQUIRED: bool = True
    OPENROUTER_API_KEY: str = ""
    POLL_INTERVAL_SECONDS: int = 10
    MAX_CONCURRENT_JOBS: int = 4
    JOB_TIMEOUT_SECONDS: int = 300
    LOG_LEVEL: str = "INFO"


def get_settings() -> Settings:
    return Settings()
