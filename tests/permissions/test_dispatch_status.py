"""Tests for the operator-facing ``scripts/dispatch_status.py`` script.

The script is read-only and runs without Django — these tests exercise
the helpers directly. The "is the env var truthy" map is duplicated
between the script and ``api.permissions._orm_dispatch.is_orm_enabled``
so a parity test catches drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def dispatch_status_module():
    """Import scripts/dispatch_status.py as a module (it isn't a package)."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import dispatch_status  # noqa: E402
    return dispatch_status


class TestIsOnTruthiness:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "YES", "on", "ON"])
    def test_truthy_values(self, monkeypatch, dispatch_status_module, value):
        monkeypatch.setenv("SOME_FLAG", value)
        assert dispatch_status_module._is_on("SOME_FLAG") is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "garbage", ""])
    def test_falsy_values(self, monkeypatch, dispatch_status_module, value):
        monkeypatch.setenv("SOME_FLAG", value)
        assert dispatch_status_module._is_on("SOME_FLAG") is False

    def test_unset_is_false(self, monkeypatch, dispatch_status_module):
        monkeypatch.delenv("SOME_FLAG", raising=False)
        assert dispatch_status_module._is_on("SOME_FLAG") is False


class TestTruthinessParityWithDispatchHelper:
    """The script's _TRUTHY map must match the dispatch helper's
    ``is_orm_enabled``. Any drift here means the operator's reported
    flag state diverges from what the dispatch logic actually does."""

    def test_truthy_set_is_identical(self, dispatch_status_module):
        from api.permissions._orm_dispatch import _TRUTHY as dispatch_truthy
        assert set(dispatch_status_module._TRUTHY) == set(dispatch_truthy)


class TestNextActionLogic:
    def test_picks_first_off_flag(self, dispatch_status_module):
        # Three flags, second is on → next is index 0 (the first off one)
        assert dispatch_status_module._next_action([False, True, False]) == 0

    def test_returns_none_when_all_on(self, dispatch_status_module):
        assert dispatch_status_module._next_action([True, True, True]) is None

    def test_first_when_all_off(self, dispatch_status_module):
        assert dispatch_status_module._next_action([False, False, False]) == 0


class TestFlagsTable:
    """The FLAGS table at the top of dispatch_status.py is the
    source-of-truth for site counts. Verify it stays in sync with
    the runbook."""

    def test_flag_names_match_dispatch_module(self, dispatch_status_module):
        """Every flag listed in the script must exist as a recognised
        flag name. The dispatch helper has a default, but accepts any
        flag string — so the check here is structural: known names."""
        names = {flag for flag, _, _ in dispatch_status_module.FLAGS}
        # These are the three flags the project has shipped.
        assert names == {
            "USE_ORM_FOR_PERMISSIONS",
            "USE_ORM_FOR_BL",
            "USE_DYNAMIC_GATEWAY",
        }

    def test_site_counts_are_positive(self, dispatch_status_module):
        for flag, n_sites, _ in dispatch_status_module.FLAGS:
            assert n_sites > 0, f"{flag} has zero sites"


class TestMainExitsCleanly:
    def test_main_returns_0_with_no_flags_set(self, monkeypatch, dispatch_status_module, capsys):
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)
        monkeypatch.delenv("SOAK_LOG_LEVEL", raising=False)

        rc = dispatch_status_module.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "USE_ORM_FOR_PERMISSIONS" in out
        assert "off" in out
        assert "next" in out  # the recommended-next-action marker

    def test_main_marks_next_action_correctly(self, monkeypatch, dispatch_status_module, capsys):
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)

        rc = dispatch_status_module.main()
        assert rc == 0
        out = capsys.readouterr().out
        # The first two should show "✓ on", USE_DYNAMIC_GATEWAY should
        # show "→ next".
        assert "USE_ORM_FOR_PERMISSIONS  ✓ on" in out
        assert "USE_ORM_FOR_BL           ✓ on" in out
        assert "USE_DYNAMIC_GATEWAY      → next" in out

    def test_main_when_all_on(self, monkeypatch, dispatch_status_module, capsys):
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")

        rc = dispatch_status_module.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "All flags ON" in out
        assert "Stage 5" in out  # mentions the deletion stage
