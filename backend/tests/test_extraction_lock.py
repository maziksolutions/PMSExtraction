from unittest.mock import patch
import pytest
from app.services.extractor import (
    set_extraction_state,
    get_extraction_state,
    get_locked_manual_ids,
    is_manual_locked_for_extraction,
)

def test_manual_locking_lifecycle():
    with patch("app.services.extractor._get_sync_redis", return_value=None):
        vessel_id = "test-vessel-lock-uuid"
        manual_1 = "manual-uuid-1"
        manual_2 = "manual-uuid-2"
        manual_other = "manual-uuid-other"

        # Initially idle, no manuals locked
        set_extraction_state(vessel_id, status="idle")
        assert is_manual_locked_for_extraction(manual_1, vessel_id) is False
        assert is_manual_locked_for_extraction(manual_2, vessel_id) is False
        assert get_locked_manual_ids(vessel_id) == set()

        # Start extraction with manual_1 and manual_2 active
        set_extraction_state(
            vessel_id,
            total=2,
            done=0,
            status="running",
            active_manual_ids=[manual_1, manual_2],
        )
        assert is_manual_locked_for_extraction(manual_1, vessel_id) is True
        assert is_manual_locked_for_extraction(manual_2, vessel_id) is True
        assert is_manual_locked_for_extraction(manual_other, vessel_id) is False
        assert get_locked_manual_ids(vessel_id) == {manual_1, manual_2}

        # When paused, still locked
        set_extraction_state(vessel_id, status="paused")
        assert is_manual_locked_for_extraction(manual_1, vessel_id) is True
        assert is_manual_locked_for_extraction(manual_2, vessel_id) is True

        # When completed, lock is released
        set_extraction_state(vessel_id, status="completed")
        assert is_manual_locked_for_extraction(manual_1, vessel_id) is False
        assert is_manual_locked_for_extraction(manual_2, vessel_id) is False
        assert get_locked_manual_ids(vessel_id) == set()

        # Reset
        set_extraction_state(vessel_id, status="idle")
