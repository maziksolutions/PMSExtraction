import asyncio
import sys
sys.path.insert(0, ".")

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'job_description_backup'
            );
        """))
        exists = res.scalar()
        if not exists:
            print("Backup table 'job_description_backup' does not exist. Cannot restore.")
            return
            
        print("Restoring job descriptions from backup...")
        await db.execute(text("""
            UPDATE jobs
            SET job_description = b.original_description
            FROM job_description_backup b
            WHERE jobs.id = b.job_id;
        """))
        await db.commit()
        print("Successfully restored all job descriptions from backup!")

if __name__ == "__main__":
    asyncio.run(main())
