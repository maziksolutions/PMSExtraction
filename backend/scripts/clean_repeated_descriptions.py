import asyncio
import sys
sys.path.insert(0, "d:\\Mazik\\maritime-pms-tool\\backend")

async def main():
    from app.core.database import AsyncSessionLocal
    from app.models.job import Job
    from app.services.job_naming import (
        strip_source_reference_footer,
        split_reference_entries,
        append_source_references_to_description
    )
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Job))
        jobs = res.scalars().all()
        print(f"Loaded {len(jobs)} jobs to clean up.")
        
        updated_count = 0
        for job in jobs:
            if not job.job_description:
                continue
                
            orig_desc = job.job_description
            reference_entries = split_reference_entries(
                pdf_reference=job.pdf_reference,
                page_reference=job.page_reference,
                source_reference=job.source_reference
            )
            stripped_desc = strip_source_reference_footer(orig_desc)
            new_desc = append_source_references_to_description(stripped_desc, reference_entries)
            
            if new_desc != orig_desc:
                job.job_description = new_desc
                db.add(job)
                updated_count += 1
                
        if updated_count > 0:
            await db.commit()
            print(f"Successfully cleaned up and deduplicated {updated_count} job descriptions!")
        else:
            print("No job descriptions required cleaning.")

if __name__ == "__main__":
    asyncio.run(main())
