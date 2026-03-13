"""Compatibility patches for Python 3.14.0rc2 + Pydantic.

Python 3.14.0rc2 removed the ``prefer_fwd_module`` parameter from
``typing._eval_type``, breaking Pydantic's type evaluation. This module
patches ``typing._eval_type`` to accept and ignore the removed parameter.

Must be imported before any Pydantic models are defined.
"""

import inspect
import sys
import typing


def _patch_typing_eval_type() -> None:
    """Make typing._eval_type accept prefer_fwd_module for Pydantic compat."""
    if sys.version_info < (3, 14):
        return

    real_eval_type = typing._eval_type  # type: ignore[attr-defined]  # noqa: SLF001
    real_params = set(inspect.signature(real_eval_type).parameters)

    if "prefer_fwd_module" in real_params:
        return

    import functools  # noqa: PLC0415

    @functools.wraps(real_eval_type)
    def patched_eval_type(  # noqa: ANN202
        *args,  # noqa: ANN002
        **kwargs,  # noqa: ANN003
    ):
        kwargs.pop("prefer_fwd_module", None)
        return real_eval_type(*args, **kwargs)

    typing._eval_type = patched_eval_type  # type: ignore[attr-defined]  # noqa: SLF001


_patch_typing_eval_type()
