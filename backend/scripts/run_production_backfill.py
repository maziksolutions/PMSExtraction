import asyncio
import sys
sys.path.insert(0, ".")

async def main():
    import scripts.backup_descriptions as backup
    import scripts.backfill_job_descriptions as backfill
    
    print("=== STEP 1: Running Backup ===")
    await backup.main()
    
    print("\n=== STEP 2: Running Backfill ===")
    await backfill.main()

if __name__ == "__main__":
    asyncio.run(main())
