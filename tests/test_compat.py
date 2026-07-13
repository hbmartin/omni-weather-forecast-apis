from __future__ import annotations

from typing import Any

import pytest

from omni_weather_forecast_apis import _compat


def test_typing_patch_is_skipped_before_python_314(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _compat.typing._eval_type
    monkeypatch.setattr(_compat.sys, "version_info", (3, 13))

    _compat._patch_typing_eval_type()

    assert _compat.typing._eval_type is original


def test_typing_patch_is_skipped_when_eval_type_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_compat.sys, "version_info", (3, 14))
    monkeypatch.delattr(_compat.typing, "_eval_type")

    _compat._patch_typing_eval_type()

    assert not hasattr(_compat.typing, "_eval_type")


def test_typing_patch_preserves_compatible_eval_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def compatible_eval_type(
        value: object,
        *,
        prefer_fwd_module: str | None = None,
    ) -> tuple[object, str | None]:
        return value, prefer_fwd_module

    monkeypatch.setattr(_compat.sys, "version_info", (3, 14))
    monkeypatch.setattr(_compat.typing, "_eval_type", compatible_eval_type)

    _compat._patch_typing_eval_type()

    assert _compat.typing._eval_type is compatible_eval_type


def test_typing_patch_discards_removed_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def current_eval_type(*args: Any, **kwargs: Any) -> object:
        calls.append((args, kwargs))
        return args[0]

    monkeypatch.setattr(_compat.sys, "version_info", (3, 14))
    monkeypatch.setattr(_compat.typing, "_eval_type", current_eval_type)

    _compat._patch_typing_eval_type()

    assert _compat.typing._eval_type("annotation", prefer_fwd_module="models") == (
        "annotation"
    )
    assert calls == [(("annotation",), {})]
