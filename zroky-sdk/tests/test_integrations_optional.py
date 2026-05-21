# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for optional integration imports."""

from __future__ import annotations

import builtins
import importlib
import sys
import types

import pytest


def _clear_langchain_core_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "langchain_core" or module_name.startswith("langchain_core."):
            sys.modules.pop(module_name, None)


def test_integrations_module_import_does_not_require_langchain() -> None:
    _clear_langchain_core_modules()
    sys.modules.pop("zroky.integrations.langchain", None)

    import zroky.integrations as integrations

    integrations = importlib.reload(integrations)
    assert "ZROKYCallbackHandler" in integrations.__all__


def test_callback_handler_access_raises_helpful_error_without_langchain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_langchain_core_modules()
    sys.modules.pop("zroky.integrations.langchain", None)

    import zroky.integrations as integrations

    integrations = importlib.reload(integrations)

    original_import = builtins.__import__

    def _blocked_import(name: str, *args: object, **kwargs: object):
        if name == "langchain_core" or name.startswith("langchain_core."):
            raise ImportError("No module named 'langchain_core'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    with pytest.raises(ImportError, match=r"pip install zroky\[langchain\]"):
        _ = integrations.ZROKYCallbackHandler


def test_callback_handler_is_available_with_langchain_core_shims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_langchain_core_modules()
    sys.modules.pop("zroky.integrations.langchain", None)

    langchain_core = types.ModuleType("langchain_core")
    callbacks = types.ModuleType("langchain_core.callbacks")
    outputs = types.ModuleType("langchain_core.outputs")

    class BaseCallbackHandler:
        pass

    class LLMResult:
        pass

    callbacks.BaseCallbackHandler = BaseCallbackHandler
    outputs.LLMResult = LLMResult

    monkeypatch.setitem(sys.modules, "langchain_core", langchain_core)
    monkeypatch.setitem(sys.modules, "langchain_core.callbacks", callbacks)
    monkeypatch.setitem(sys.modules, "langchain_core.outputs", outputs)

    import zroky.integrations as integrations

    integrations = importlib.reload(integrations)
    callback_handler = integrations.ZROKYCallbackHandler

    assert callback_handler.__name__ == "ZROKYCallbackHandler"
    assert issubclass(callback_handler, BaseCallbackHandler)
