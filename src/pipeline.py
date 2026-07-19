"""
BIRD Mini-Dev Text-to-SQL 파이프라인
NLQ + Schema + hint -> LLM -> SQL
"""

import os
import re
import json
import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from prompts import get_schema_text, build_prompt

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEV_JSON = ROOT / "data" / "mini_dev_data" / "mini_dev_sqlite.json"
DEFAULT_DB_ROOT = ROOT / "data" / "mini_dev_data" / "dev_databases"


# TODO 1 : OpenAI client 초기화
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def clean_sql(raw_output: str) -> str:

    # TODO 2: LLM 출력에서 SQL만 추출 (```sql ... ``` 제거)
    raw_output = raw_output.replace("```sql", "").replace("```", "")
    return raw_output.strip()


def call_llm(prompt: str, model: str) -> str:
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 2000,
    }
    # gpt-5 계열, o-series 등 reasoning 모델은 temperature 커스텀 값을 지원 안 함 (기본값만 허용)
    if not model.startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["temperature"] = 0.0

    response = client.chat.completions.create(**kwargs)
    return clean_sql(response.choices[0].message.content)


def run_pipeline(model: str, dev_json: Path, db_root: Path, limit: int = None, hard_only: bool = False):
    # 1. json 로드
    with open(dev_json, "r") as f:
        data = json.load(f)

    # 2. hard_only 필터링
    if hard_only:
        data = [d for d in data if d.get("difficulty") == "challenging"]

    # limit 적용
    if limit:
        data = data[:limit]

    predictions = []

    # 3. 각 문항 순회하면서 처리 (tqdm으로 감싸면 진행바가 뜸)
    for item in tqdm(data, desc=f"Running {model}"):
        db_id = item["db_id"]
        question = item["question"]
        hint = item.get("evidence", "")
        question_id = item.get("question_id")

        db_path = db_root / db_id / f"{db_id}.sqlite"
        schema_text = get_schema_text(str(db_path))
        prompt = build_prompt(question, schema_text, hint)

        # 4. LLM 호출 (실패해도 전체가 안 멈추게 try/except)
        try:
            predicted_sql = call_llm(prompt, model)
        except Exception as e:
            predicted_sql = f"ERROR: {e}"

        predictions.append({
            "question_id": question_id,
            "db_id": db_id,
            "question": question,
            "evidence": hint,
            "gold_sql": item.get("SQL", ""),
            "predicted_sql": predicted_sql,
            "model": model,
        })

    # 5. 결과를 json 파일로 저장
    safe_model_name = model.replace("/", "_")
    output_path = ROOT / "results" / f"predictions_{safe_model_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)

    print(f"\n저장 완료: {output_path} ({len(predictions)}개)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-4o-mini", help="사용할 모델명")
    parser.add_argument("--dev-json", type=Path, default=DEFAULT_DEV_JSON, help="mini_dev_sqlite.json 경로")
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT, help="dev_databases 폴더 경로")
    parser.add_argument("--limit", type=int, default=None, help="테스트할 문항 수 제한")
    parser.add_argument("--hard-only", action="store_true", help="difficulty가 challenging인 것만 실행")
    args = parser.parse_args()

    run_pipeline(
        model=args.model,
        dev_json=args.dev_json,
        db_root=args.db_root,
        limit=args.limit,
        hard_only=args.hard_only,
    )
