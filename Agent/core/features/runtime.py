from __future__ import annotations

import functools
from typing import Callable, Optional

from core.features.flags import FeatureFlag, FeatureFlagSystem


class FeatureDisabled(RuntimeError):
    pass


def require_flag(flag: FeatureFlag, flags: Optional[FeatureFlagSystem] = None):
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            fs = flags
            if fs is None:
                fs = getattr(args[0], "feature_flags", None) if args else None
            if fs is None or not fs.is_enabled(flag):
                raise FeatureDisabled(
                    f"Feature {flag.value} is disabled. "
                    f"Enable it with: feature_flags.enable(FeatureFlag.{flag.name})"
                )
            return await fn(*args, **kwargs)

        return wrapper

    return decorator

