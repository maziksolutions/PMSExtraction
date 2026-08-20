import asyncio
import sys
sys.path.insert(0, "d:\\Mazik\\maritime-pms-tool\\backend")

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    
    async with AsyncSessionLocal() as db:
        # Check if the backup table exists
        res = await db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'job_name_backup'
            );
        """))
        exists = res.scalar()
        if not exists:
            print("Backup table 'job_name_backup' does not exist! Cannot restore.")
            return
            
        res = await db.execute(text("SELECT COUNT(*) FROM job_name_backup;"))
        count = res.scalar()
        print(f"Found {count} backed up job titles in 'job_name_backup'.")
        if count == 0:
            print("No backup records found. Cannot restore.")
            return
            
        print("Restoring original job titles in 'jobs' table...")
        await db.execute(text("""
            UPDATE jobs
            SET job_name = b.original_job_name
            FROM job_name_backup b
            WHERE jobs.id = b.job_id;
        """))
        await db.commit()
        print("Successfully restored all original job titles!")

if __name__ == "__main__":
    asyncio.run(main())
