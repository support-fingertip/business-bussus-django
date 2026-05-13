"""Domain-handler base class + registry.

Every per-domain handler subclasses :class:`DomainHandler`, declares
the ``object_name`` values it serves via ``OBJECT_NAMES``, and
implements only the HTTP-verb methods it actually handles.

Registration
------------

Handlers register themselves via the :func:`register` decorator at
import time. ``api/BL/handlers/__init__.py`` imports each handler
module so the side-effect registration runs. Adding a new handler
means: (1) write the class, (2) decorate with ``@register``, (3)
add the import to the package ``__init__``.

Sentinel for "not handled by this handler"
------------------------------------------

A verb method that the handler doesn't implement returns the module
sentinel :data:`NotImplementedForVerb`. ``BusinessLogicHandler``
treats that as "fall back to legacy inline dispatch" rather than as
a real return value. We can't use ``NotImplemented`` (the Python
built-in) because it has special semantics in arithmetic; we can't
use ``None`` because some legacy paths legitimately return ``None``.
"""

from __future__ import annotations

from typing import Any


class HandlerNotFound(LookupError):
    """Raised when a lookup expects a registered handler and finds none."""


class _NotImplementedForVerb:
    """Sentinel — returned by base-class verb methods. Caller falls back to legacy."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<NotImplementedForVerb>"

    def __bool__(self) -> bool:
        # Make sure ``if result:`` short-circuits cleanly even if a
        # caller forgets the explicit identity check.
        return False


NotImplementedForVerb = _NotImplementedForVerb()


# {object_name: HandlerClass}
HANDLER_REGISTRY: dict[str, type["DomainHandler"]] = {}


def register(cls: type["DomainHandler"]) -> type["DomainHandler"]:
    """Decorator — register ``cls`` for every name in ``cls.OBJECT_NAMES``.

    Catches duplicate registrations so two handlers can't silently
    fight over the same object name.
    """
    if not getattr(cls, "OBJECT_NAMES", None):
        raise TypeError(
            f"{cls.__name__} must declare OBJECT_NAMES (a non-empty tuple)"
        )
    for name in cls.OBJECT_NAMES:
        existing = HANDLER_REGISTRY.get(name)
        if existing is not None and existing is not cls:
            raise RuntimeError(
                f"Two handlers registered for object_name={name!r}: "
                f"{existing.__name__} and {cls.__name__}"
            )
        HANDLER_REGISTRY[name] = cls
    return cls


def get_handler(object_name: str) -> type["DomainHandler"] | None:
    """Return the registered handler class for ``object_name``, or ``None``."""
    return HANDLER_REGISTRY.get(object_name)


class DomainHandler:
    """Abstract base — per-domain BL handler.

    Subclasses set ``OBJECT_NAMES`` to the tuple of object names they
    serve, then override the verb methods they actually implement.
    Verbs they don't implement return :data:`NotImplementedForVerb`
    so :class:`api.BL.blcontroller.BusinessLogicHandler` can fall
    back to its legacy inline dispatch.
    """

    OBJECT_NAMES: tuple[str, ...] = ()

    def __init__(self, request, object_name: str):
        self.request = request
        self.object_name = object_name

    # ----- HTTP verbs --------------------------------------------------

    def get(self, **kwargs: Any) -> Any:
        return NotImplementedForVerb

    def post(self, data: Any, **kwargs: Any) -> Any:
        return NotImplementedForVerb

    def patch(self, data: Any, **kwargs: Any) -> Any:
        return NotImplementedForVerb

    def delete(self, data: Any, **kwargs: Any) -> Any:
        return NotImplementedForVerb
