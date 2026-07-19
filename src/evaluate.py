"""
EX (Execution Accuracy) 계산 + 오답 케이스 추출
predicted_sql 과 gold_sql 을 각각 실행해서 결과가 일치하는지 비교한다.
(BIRD 공식 방식: 문자열 매칭이 아니라 "실행 결과" 비교)

사용법:
    python evaluate.py --predictions ../results/predictions_gpt-4o-mini.json
"""

import json
import time
import sqlite3
import argparse
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_ROOT = ROOT / "data" / "mini_dev_data" / "dev_databases"


def execute_sql(db_path: str, sql: str, timeout: float = 15.0):
    """
    SQL 실행 결과를 반환. 에러/타임아웃 나면 None 반환.

    주의: sqlite3.connect(db_path, timeout=...) 의 timeout은
    "DB 락 대기시간"이지 "쿼리 실행시간 제한"이 아니다.
    LLM이 만든 SQL이 JOIN 조건을 빼먹는 등 잘못 짜여지면
    Cartesian product가 발생해서 사실상 끝나지 않을 수 있다.
    그래서 sqlite3의 progress_handler를 이용해 진짜 실행시간 제한을 건다.
    """
    try:
        conn = sqlite3.connect(db_path)
        start_time = time.time()

        def handler():
            if time.time() - start_time > timeout:
                return 1  # 0이 아닌 값을 리턴하면 실행이 중단됨
            return 0

        conn.set_progress_handler(handler, 1000)  # 1000 VM instruction마다 체크
        cursor = conn.cursor()
        cursor.execute(sql)
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception:
        return None


def is_correct(db_path: str, predicted_sql: str, gold_sql: str) -> bool:
    pred_result = execute_sql(db_path, predicted_sql)
    gold_result = execute_sql(db_path, gold_sql)

    if pred_result is None or gold_result is None:
        return False  # 실행 자체가 안 되거나 타임아웃이면 무조건 오답
        # (gold_sql이 실패하는 경우는 드물지만, 타임아웃 등으로 발생 가능)

    # 순서는 무시하고 값 집합만 비교 (BIRD 공식 evaluator와 동일한 방식)
    return set(pred_result) == set(gold_result)


def run_evaluation(predictions_path: Path, db_root: Path):
    with open(predictions_path, "r") as f:
        predictions = json.load(f)

    correct = 0
    wrong_cases = []

    for item in tqdm(predictions, desc="Evaluating"):
        db_id = item["db_id"]
        db_path = db_root / db_id / f"{db_id}.sqlite"

        ok = is_correct(str(db_path), item["predicted_sql"], item["gold_sql"])
        item["is_correct"] = ok

        if ok:
            correct += 1
        else:
            wrong_cases.append(item)

    ex_score = correct / len(predictions) * 100 if predictions else 0.0
    print(f"\nEX (Execution Accuracy): {ex_score:.2f}%  ({correct}/{len(predictions)})")

    # 정오답 표시를 포함해서 원본 predictions 파일 갱신
    with open(predictions_path, "w") as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)

    # 오답만 따로 저장 -> 여기서 10개 골라서 에러 분석 진행
    wrong_path = ROOT / "results" / "error_analysis" / "wrong_cases.json"
    wrong_path.parent.mkdir(parents=True, exist_ok=True)
    with open(wrong_path, "w") as f:
        json.dump(wrong_cases, f, ensure_ascii=False, indent=2)

    print(f"오답 {len(wrong_cases)}개 저장: {wrong_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, type=Path, help="pipeline.py가 만든 predictions json 경로")
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT, help="dev_databases 폴더 경로")
    args = parser.parse_args()

    run_evaluation(args.predictions, args.db_root)
