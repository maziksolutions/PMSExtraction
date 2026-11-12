import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.models.ingestion import Manual, ManualStatus
from app.api.v1.ingestion import get_manual_page_status

@pytest.mark.asyncio
async def test_get_manual_page_status():
    vessel_id = uuid.uuid4()
    manual_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = tenant_id

    manual = MagicMock(spec=Manual)
    manual.id = manual_id
    manual.vessel_id = vessel_id
    manual.tenant_id = tenant_id
    manual.original_filename = "102# PV VALVE光伏阀.pdf"
    manual.page_count = 60
    manual.status = ManualStatus.classified
    manual.target_model = "PV-01"
    manual.pages_with_components_physical = "58-59"
    manual.pages_with_components = "58-59"
    manual.pages_with_jobs_physical = ""
    manual.pages_with_jobs = ""
    manual.pages_with_spares_physical = "58-59"
    manual.pages_with_spares = "58-59"

    db = AsyncMock()

    class MockResult:
        def __init__(self, val):
            self._val = val
        def scalar_one_or_none(self):
            return self._val
        def scalars(self):
            m = MagicMock()
            m.all.return_value = self._val if isinstance(self._val, list) else []
            return m
        def all(self):
            return self._val if isinstance(self._val, list) else []

    async def mock_execute(query, params=None):
        query_str = str(query).lower()
        if "vessel_projects" in query_str:
            vessel = MagicMock()
            vessel.id = vessel_id
            return MockResult(vessel)
        elif "manuals" in query_str:
            return MockResult(manual)
        elif "components" in query_str:
            return MockResult([])
        elif "jobs" in query_str:
            return MockResult([])
        elif "spares" in query_str:
            return MockResult([])
        return MockResult(None)

    db.execute.side_effect = mock_execute

    # Test with empty strings for unsaved params (should fall back to saved DB fields!)
    res = await get_manual_page_status(
        vessel_id=vessel_id,
        manual_id=manual_id,
        current_user=user,
        db=db,
        components_pages_unsaved="",
        jobs_pages_unsaved="",
        spares_pages_unsaved="",
    )

    assert res["manual_id"] == str(manual_id)
    assert res["original_filename"] == "102# PV VALVE光伏阀.pdf"
    assert res["status"] == "classified"
    assert len(res["pages"]) == 2
    assert res["pages"][0]["page_number"] == 58
    assert res["pages"][0]["is_targeted"] is True
    assert res["pages"][1]["page_number"] == 59
    assert res["pages"][1]["is_targeted"] is True
