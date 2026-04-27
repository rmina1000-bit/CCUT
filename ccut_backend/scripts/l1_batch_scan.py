import asyncio
import os
import sys

# ?꾨줈?앺듃 猷⑦듃瑜?寃쎈줈??異붽?
sys.path.append(r"D:\CCUT_1.0.3\ccut_backend")

from database import SessionLocal
from engine.l1_scanner import l1_scanner
from archive.db_models import SourceTable, FragmentTable

async def batch_scan():
    db = SessionLocal()
    try:
        # 援?갑 ?ㅼ쬆???뚯뒪??寃??
        sources = db.query(SourceTable).filter(SourceTable.source_id.like("SRC_DEFENSE_%")).all()
        print(f"[Batch] Found {len(sources)} sources to scan.")
        
        for source in sources:
            # ?대? 遺꾪븷???댁슜???덈뒗吏 ?뺤씤
            existing = db.query(FragmentTable).filter_by(source_id=source.source_id).first()
            if existing:
                print(f"[Batch] Skipping {source.source_id} - already scanned.")
                continue
                
            print(f"[Batch] Scanning {source.source_id} ({source.title})...")
            try:
                # L1 ?ㅼ틪 ?ㅽ뻾 (?λ㈃ 遺꾩꽍 -> 議곌컖 ?앹꽦 -> DB ???
                fragments = await l1_scanner.scan(source.source_id, db)
                print(f"[Batch] Successfully created {len(fragments)} fragments for {source.source_id}")
            except Exception as e:
                print(f"[Batch] Error scanning {source.source_id}: {e}")
                
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(batch_scan())

