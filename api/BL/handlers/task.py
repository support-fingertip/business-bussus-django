"""TaskHandler — first per-domain handler extracted from blcontroller.py.

Replaces two inline dispatch branches in ``BusinessLogicHandler``:

  * GET   ``elif self.object_name == 'task':``    (was ~line 1836)
  * PATCH ``elif self.object_name == 'task':``    (was ~line 4438)

The Task POST path in legacy code (``another_object == 'task'`` at
~line 2790) is intentionally NOT extracted in wave 1. That branch is
in a "create a child task under self.object_name" context — the
PARENT's object_name drives the dispatch, not Task's. Moving it
needs the parent handlers (Lead, Contact, etc.) to be extracted
first so the child-creation logic can land in their files. The
registry lookup is keyed on ``self.object_name`` and would not
trigger for the another_object path; POST stays in legacy
blcontroller for now.

Behaviour is intentionally byte-identical to the legacy code. The
only change is the location: this file owns Task GET + PATCH;
blcontroller.py delegates here via the handler registry.

Wave 1 of the god-file split. Future waves extract more domains the
same way; blcontroller.py shrinks each time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.BL.handlers._base import DomainHandler, register
from api.BL.task import get_related_tasks
from api.permissions.permissions import (
    get_permissions,
    patch_permission,
)


_TASK_GET_FIELDS = [
    "assigned_to_id",
    "due_date",
    "status",
    "subject",
    "related_to_object_id",
    "assigned_to.name",
    "created_date",
    "last_modified_date",
    "created_by_id",
    "last_modified_by_id",
    "created_by.name",
    "last_modified_by.name",
]


@register
class TaskHandler(DomainHandler):
    """Per-tenant task / to-do BL.

    GET fetches a single task by id (full field list) or returns
    related tasks for a parent record.

    POST creates a task linked to a parent record (the "another_object
    == 'task'" path in legacy code). The parent passes its own
    object_name as ``self.object_name``; the task itself is the
    ``another_object``.

    PATCH stamps ``last_modified_*`` fields and delegates to
    ``patch_permission``.
    """

    OBJECT_NAMES = ("task",)

    # ------------------------------------------------------------------
    # GET — was blcontroller.py:1836-1852
    # ------------------------------------------------------------------
    def get(self, **kwargs: Any) -> Any:
        record_id = self.request.GET.get("id")

        if record_id:
            try:
                tasks = get_permissions(
                    self.request,
                    tableName="task",
                    id=record_id,
                    fields=_TASK_GET_FIELDS,
                    **kwargs,
                ).get("data", [])
                return tasks
            except Exception as e:
                print(str(e))
                raise Exception(str(e))

        # No id → return tasks related to the parent record.
        return get_related_tasks(id=record_id, **kwargs)

    # ------------------------------------------------------------------
    # PATCH — was blcontroller.py:4438-4442
    # ------------------------------------------------------------------
    def patch(self, data: Any, **kwargs: Any) -> Any:
        update_data_ = data
        user_id = kwargs.get("user_", {}).get("id")
        update_data_["last_modified_by_id"] = user_id
        update_data_["last_modified_date"] = datetime.now()
        return patch_permission(
            self.request,
            self.object_name,
            update_data=update_data_,
            **kwargs,
        )
