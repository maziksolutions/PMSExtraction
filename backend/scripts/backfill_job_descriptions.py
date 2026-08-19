import asyncio
import sys
sys.path.insert(0, ".")

async def main():
    from app.core.database import AsyncSessionLocal
    from app.models.job import Job
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Job).where(Job.job_description.is_not(None)))
        jobs = res.scalars().all()
        
        print(f"Loaded {len(jobs)} jobs to backfill.")
        updated_count = 0
        for job in jobs:
            if not job.job_description:
                continue
            orig = job.job_description
            # Trigger the SQLAlchemy validates hook to apply /*- formatting
            job.job_description = orig
            if job.job_description != orig:
                db.add(job)
                updated_count += 1
                
        if updated_count > 0:
            await db.commit()
            print(f"Successfully backfilled and formatted {updated_count} existing job descriptions in the database!")
        else:
            print("No updates needed.")

if __name__ == "__main__":
    asyncio.run(main())
