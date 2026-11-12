import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.ingestion import Manual, ManualStatus
from app.api.v1.manuals import _manual_order_expr, get_untouched_manuals


def test_manual_order_expr_iteration():
    expr_asc = _manual_order_expr("batch_number", "asc")
    expr_desc = _manual_order_expr("iteration", "desc")
    expr_batch = _manual_order_expr("batch", "desc")

    assert str(expr_asc) == "manuals.batch_number ASC"
    assert str(expr_desc) == "manuals.batch_number DESC"
    assert str(expr_batch) == "manuals.batch_number DESC"


@pytest.mark.asyncio
async def test_get_untouched_manuals_endpoint():
    vessel_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = tenant_id

    # Manual 1: never run (0 runs, 0 extracted)
    m1 = MagicMock(spec=Manual)
    m1.id = uuid.uuid4()
    m1.vessel_id = vessel_id
    m1.tenant_id = tenant_id
    m1.original_filename = "Untouched_Manual_1.pdf"
    m1.category = "Main Engine"
    m1.target_model = "6EY18ALW"
    m1.batch_number = 2
    m1.created_at = None
    m1.file_size_bytes = 102400
    m1.useful_for_extraction = "yes"
    m1.status = ManualStatus.classified
    m1.pages_with_components_physical = "10-12"
    m1.pages_with_components = "10-12"
    m1.pages_with_jobs_physical = "15"
    m1.pages_with_jobs = "15"
    m1.pages_with_spares_physical = "20-25"
    m1.pages_with_spares = "20-25"

    # Manual 2: has run count 1 and extracted items
    m2 = MagicMock(spec=Manual)
    m2.id = uuid.uuid4()
    m2.vessel_id = vessel_id
    m2.tenant_id = tenant_id
    m2.original_filename = "Processed_Manual_2.pdf"
    m2.category = "Aux Engine"
    m2.target_model = None
    m2.batch_number = 1
    m2.created_at = None
    m2.file_size_bytes = 204800
    m2.useful_for_extraction = "yes"
    m2.status = ManualStatus.classified
    m2.pages_with_components_physical = "1"
    m2.pages_with_components = "1"
    m2.pages_with_jobs_physical = "2"
    m2.pages_with_jobs = "2"
    m2.pages_with_spares_physical = "3"
    m2.pages_with_spares = "3"

    db = AsyncMock()

    class MockResult:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            return self
        def all(self):
            return self.items
        def fetchall(self):
            return self.items
        def fetchone(self):
            return self.items[0] if self.items else None
        def scalar_one_or_none(self):
            return self.items[0] if self.items else None

    # Call 1: _get_vessel_or_404
    # Call 2: select(Manual) -> [m1, m2]
    # Call 3: SELECT manual_id, run_count FROM manual_extraction_runs -> [(m2.id, 1)]
    # Call 4: select(Component) -> [(m2.id, 1)]
    # Call 5: select(Job) -> [(m2.id, 2)]
    # Call 6: select(Spare) -> [(m2.id, 3)]
    db.execute.side_effect = [
        MockResult([MagicMock()]),          # vessel check
        MockResult([m1, m2]),               # manuals
        MockResult([(m2.id, 1)]),           # run counts
        MockResult([(m2.id, 1)]),           # comp_res
        MockResult([(m2.id, 2)]),           # job_res
        MockResult([(m2.id, 3)]),           # spare_res
    ]

    res = await get_untouched_manuals(
        vessel_id=vessel_id,
        current_user=user,
        db=db,
    )

    assert res["total_untouched"] == 1
    assert len(res["manuals"]) == 1
    untouched = res["manuals"][0]
    assert untouched["id"] == str(m1.id)
    assert untouched["original_filename"] == "Untouched_Manual_1.pdf"
    assert untouched["batch_number"] == 2
    assert untouched["is_never_run"] is True
    assert untouched["targeted_components_count"] == 3
    assert untouched["targeted_jobs_count"] == 1
    assert untouched["targeted_spares_count"] == 6
