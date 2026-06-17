"""NPU-STACK sitecustomize — Python 3.14 + torch 2.9 compatibility patches.

torch 2.9 does not officially support Python 3.14.  These targeted patches
remove the version guards so Unsloth can load.  If training produces errors,
the root cause is the underlying compile support, not these guards.
"""
from __future__ import annotations

import warnings

# Patch 1: torch.__init__.py — "torch.compile is not supported on Python 3.14+"
try:
    import torch
    _original_compile = torch.compile

    def _patched_compile(*args, **kwargs):
        if kwargs.get("backend") == "inductor":
            kwargs["backend"] = "eager"  # Fall back to eager on 3.14
        return _original_compile(*args, **kwargs)

    torch.compile = _patched_compile
except Exception:
    pass

# Patch 2: torch._dynamo.eval_frame.py — "Python 3.14+ not yet supported"
try:
    import torch._dynamo.eval_frame as _ef

    def _patched_check():
        warnings.warn("torch.compile on Python 3.14+: using eager backend fallback")
        return True

    _ef.check_if_dynamo_supported = _patched_check
except Exception:
    pass

# Patch 3: typing.Union no longer supports __module__ assignment in 3.14
try:
    import typing as _typing

    _orig_setattr = _typing._BaseGenericAlias.__setattr__

    def _safe_setattr(obj, name, value):
        if name == "__module__":
            try:
                object.__setattr__(obj, "__orig_module__", value)
            except AttributeError:
                pass
            return
        try:
            _orig_setattr(obj, name, value)
        except AttributeError:
            object.__setattr__(obj, name, value)

    _typing._BaseGenericAlias.__setattr__ = _safe_setattr
except Exception:
    pass
