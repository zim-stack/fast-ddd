from __future__ import annotations

from types import ModuleType

try:
    import attrs as _attrs
except (
    ModuleNotFoundError
):  # narrower than ImportError, so a broken install still surfaces
    _attrs: ModuleType | None = None

# Shared code that only needs to know whether attrs is available should check this flag
HAS_ATTRS: bool = _attrs is not None


def require_attrs() -> ModuleType:
    """Return the attrs module, or raise ImportError with install instructions.

    Call this where attrs is needed. Modules that exist only for the attrs
    flavor can call it at import time, because they are loaded only when that
    flavor is requested. Code loaded by default should call it inside the
    function that uses attrs, so importing the library never requires attrs.

    Example:
        def make_state_class(name: str):
            attrs = require_attrs()
            return attrs.make_class(name, {}, frozen=True)
    """
    if _attrs is None:
        raise ImportError(
            "This feature needs the optional dependency 'attrs' "
            '(pip install "fast-ddd[attrs]"). '
            "Use dataclass alternatives to stay on the standard library."
        )
    return _attrs
