import json
import os
import requests
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.llm_client import get_llm_client

class ErrorAnalysisResult(BaseModel):
    model_config = ConfigDict(strict=False)

    is_hallucinated: bool = Field(..., description="Whether the error seems like a hallucinated/fake error log")
    root_cause: str = Field(..., description="The direct root cause of the error")
    suggested_fix: str = Field(..., description="The suggested developer fix")
    severity: str = Field(..., description="Severity level: LOW, MEDIUM, HIGH, or CRITICAL")

class ErrorAiParser:
    def __init__(self):
        try:
            self.client = get_llm_client()
        except Exception:
            # Failure to construct the LLM client (missing API key, etc.)
            # should not crash import time. Defer functionality to runtime.
            self.client = None

    def analyze_error_with_deepseek(self, error_log: str, retries: int = 2) -> Optional[dict]:
        """
        Takes raw error log, uses DeepSeek V4 via OpenRouter for strict JSON parsing,
        applies Zero-Hallucination temperature (0.0), and uses self-healing retries if it fails.
        """
        if not self.client:
            print("Warning: OPENROUTER_API_KEY not set. Skipping AI analysis.")
            return None

        system_prompt = (
            "You are a Senior Architect and expert Error Log Analyzer. "
            "Analyze the provided error log. "
            "You MUST respond ONLY in strictly valid JSON matching the exact schema.\n"
            'Expected schema: {"is_hallucinated": bool, "root_cause": str, "suggested_fix": str, "severity": "LOW"|"MEDIUM"|"HIGH"|"CRITICAL"}'
        )
        
        current_error_context = ""
        
        for attempt in range(retries + 1):
            try:
                # 1. API Call with Zero Hallucination Config & Strict JSON Mode
                prompt_messages = [
                    {"role": "system", "content": system_prompt + current_error_context},
                    {"role": "user", "content": f"Analyze this error log:\n\n{error_log}"}
                ]
                
                response = self.client.chat_completions_create(
                    messages=prompt_messages,
                    temperature=0.0, # Zero Hallucination Strategy
                    response_format={"type": "json_object"} # Strict JSON Mode
                )

                response_content = response.choices[0].message.content
                
                # Parse JSON
                raw_data = json.loads(response_content)
                
                # 2. Validation (Pydantic Safeguard)
                validated_data = ErrorAnalysisResult(**raw_data)
                
                # Return the verified dict
                return validated_data.model_dump()

            except (json.JSONDecodeError, ValidationError) as e:
                if attempt == retries:
                    # Final attempt failed
                    print(f"Failed to get valid JSON from DeepSeek after {retries} retries.")
                    return None
                    
                # 3. SELF-HEALING LOOP
                current_error_context = f"\n\nYour previous attempt failed with error: {str(e)}. Please FIX your JSON structure to strictly match the expected schema."
                print(f"Self-healing attempt {attempt + 1} triggered...")

_error_ai_parser_singleton: Optional[ErrorAiParser] = None


def get_error_ai_parser() -> Optional[ErrorAiParser]:
    """Return a cached ErrorAiParser instance or None if unavailable.

    Avoids import-time LLM initialization so the application can start
    without provider API keys present. Callers should handle a None
    return value by skipping AI-powered analysis.
    """
    global _error_ai_parser_singleton
    if _error_ai_parser_singleton is None:
        _error_ai_parser_singleton = ErrorAiParser()
    return _error_ai_parser_singleton
