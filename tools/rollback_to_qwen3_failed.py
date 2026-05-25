import sqlite3

def main():
    conn = sqlite3.connect('ccut_backend/ccut_app.db')
    cursor = conn.cursor()
    
    # Qwen3 실패 상태로 롤백
    cursor.execute("""
        UPDATE evidence_board 
        SET text = NULL, 
            fallback_reason = 'asr_rejected:empty_text', 
            metadata_json = '{"asr_provider": "qwen3_asr", "asr_has_text": false}' 
        WHERE source_id = 'SRC_CB9107CA'
    """)
    conn.commit()
    print('Cleared and rolled back:', conn.total_changes, 'rows')
    conn.close()

if __name__ == "__main__":
    main()
