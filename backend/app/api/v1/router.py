from fastapi import APIRouter

from app.api.v1 import auth, users, vessels

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(vessels.router, prefix="/vessels", tags=["Vessels"])

# Sprint 2
from app.api.v1 import ingestion  # noqa: E402
api_router.include_router(ingestion.router, prefix="/vessels", tags=["Ingestion"])

# Sprint 3
from app.api.v1 import manuals  # noqa: E402
api_router.include_router(manuals.router, prefix="/vessels", tags=["Manuals"])

# Sprint 4
from app.api.v1 import components  # noqa: E402
api_router.include_router(components.router, prefix="/vessels", tags=["Components"])

# Sprint 5
from app.api.v1 import jobs  # noqa: E402
api_router.include_router(jobs.router, prefix="/vessels", tags=["Jobs"])

# Sprint 6
from app.api.v1 import spares  # noqa: E402
api_router.include_router(spares.router, prefix="/vessels", tags=["Spares"])

# Sprint 7
from app.api.v1 import standard_jobs  # noqa: E402
api_router.include_router(standard_jobs.router, tags=["Standard Jobs"])

# Sprint 8
from app.api.v1 import locking, activity  # noqa: E402
api_router.include_router(locking.router, prefix="/vessels", tags=["Locking"])
api_router.include_router(activity.router, prefix="/vessels", tags=["Activity"])

# Sprint 9
from app.api.v1 import export  # noqa: E402
api_router.include_router(export.router, tags=["Export"])

# Sprint 10
from app.api.v1 import assistant  # noqa: E402
api_router.include_router(assistant.router, prefix="/vessels", tags=["AI Assistant"])

# Sprint 11
from app.api.v1 import feedback  # noqa: E402
api_router.include_router(feedback.router, tags=["Feedback"])

# Sprint 12
from app.api.v1 import admin  # noqa: E402
api_router.include_router(admin.router, tags=["Admin"])

# Addendum A
from app.api.v1 import extraction, library, precheck  # noqa: E402
api_router.include_router(extraction.router, prefix="/vessels", tags=["Extraction"])
api_router.include_router(extraction.router, tags=["ExtractionPrompts"])
api_router.include_router(library.router, tags=["Library"])
api_router.include_router(precheck.router, prefix="/vessels", tags=["PreCheck"])

# Maker/Model Library
from app.api.v1 import maker_models  # noqa: E402
api_router.include_router(maker_models.router, tags=["MakerModels"])

# Job Rank Library
from app.api.v1 import job_ranks  # noqa: E402
api_router.include_router(job_ranks.router, tags=["JobRanks"])
