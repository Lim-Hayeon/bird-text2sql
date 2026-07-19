"""
Prompt 생성 관련 함수
NLQ(question) + Schema + hint(evidence) 를 하나의 prompt로 합치는 역할
"""

import sqlite3

def get_schema_text(db_path: str) -> str:
    # TODO 1: SQLite DB 파일에서 스키마를 읽어와서 문자열로 반환

    conn  = sqlite3.connect(db_path)  # SQLite DB 파일 열기
    cursor = conn.cursor() 
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL;")
    rows = cursor.fetchall()
    schemas = [row[0] for row in rows]
    conn.close()
    return "\n\n".join(schemas) # 각 테이블의 CREATE TABLE 문을 두 줄씩 띄워서 합쳐서 반환


    


def build_prompt(question: str, schema_text: str, hint: str = "") -> str:
    # TODO 2: NLQ + Schema + hint를 하나의 prompt로 합치기'
    if hint:
        hint_section = f"Hint:\n{hint}\n\n"
    else:
        hint_section = ""

    prompt = f"Question: {question}\n\nSchema:\n{schema_text}\n\n{hint_section}Please write the SQL query.\nReturn ONLY the SQL query, with no explanation and no markdown formatting."
    return prompt
