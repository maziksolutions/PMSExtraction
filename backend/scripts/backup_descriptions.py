import asyncio
import sys
sys.path.insert(0, ".")

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS job_description_backup (
                job_id UUID PRIMARY KEY,
                original_description TEXT,
                backed_up_at TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        await db.commit()
        
        res = await db.execute(text("SELECT COUNT(*) FROM job_description_backup;"))
        count = res.scalar()
        if count > 0:
            print(f"Backup table already contains {count} records. Skipping to prevent overwriting original backup.")
            return
            
        print("Backing up current job descriptions...")
        await db.execute(text("""
            INSERT INTO job_description_backup (job_id, original_description)
            SELECT id, job_description FROM jobs
            WHERE job_description IS NOT NULL;
        """))
        await db.commit()
        
        res = await db.execute(text("SELECT COUNT(*) FROM job_description_backup;"))
        new_count = res.scalar()
        print(f"Successfully backed up {new_count} job descriptions into 'job_description_backup' table!")

if __name__ == "__main__":
    asyncio.run(main())
