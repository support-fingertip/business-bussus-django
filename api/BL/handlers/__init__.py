"""Per-domain BL handlers — wave 1 of the god-file split.

Background
----------

``api/BL/blcontroller.py`` was originally a 5,088-line god class
(``BusinessLogicHandler``) with four enormous methods (``get/post/
patch/delete_business_logic``) that dispatched on
``self.object_name`` across 150+ branches. The original Phase 4 plan
called for splitting this into per-domain handlers (TaskBL,
RecycleBinBL, FileBL, etc.) of ≤400 lines each, with
blcontroller.py becoming a thin router (≤200 lines).

That split was deferred during the Phase 0-4 ORM cutover. This
package is wave 1 of that work.

Pattern
-------

Each domain handler is a class inheriting from
:class:`DomainHandler`. It declares which ``object_name`` values it
serves via the ``OBJECT_NAMES`` class attribute. The
:func:`get_handler` lookup returns the first registered handler for
a given object name, or ``None`` if no handler is registered.

``BusinessLogicHandler`` checks the registry first; if there's a hit
it delegates to the handler, otherwise it falls back to its legacy
inline dispatch. This means handlers can be extracted one at a time
without breaking the unhandled paths.

Handlers implement only the verbs they actually serve. A handler
that only does GET doesn't need to override ``post``/``patch``/
``delete``; the base class returns ``NotImplemented`` and the
caller (BusinessLogicHandler) falls back to legacy.

Wave 1 ships:
  * ``DomainHandler`` ABC with the four-verb contract
  * ``HANDLER_REGISTRY`` and ``register`` / ``get_handler`` helpers
  * One concrete handler — ``TaskHandler`` — as proof-of-concept
"""

from __future__ import annotations

from api.BL.handlers._base import (  # noqa: F401
    DomainHandler,
    HANDLER_REGISTRY,
    HandlerNotFound,
    NotImplementedForVerb,
    get_handler,
    register,
)
from api.BL.handlers.task import TaskHandler  # noqa: F401  — registers via decorator


__all__ = [
    "DomainHandler",
    "HANDLER_REGISTRY",
    "HandlerNotFound",
    "NotImplementedForVerb",
    "get_handler",
    "register",
    "TaskHandler",
]
