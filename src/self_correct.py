"""
Self-Correction 실험: toxicology DB

목적:
    baseline predicted_sql을 gold와 비교하지 않고 '그냥 실행만' 해본 뒤,
    그 실행 결과(에러 메시지 or 결과 row)를 LLM에게 다시 보여주고
    "정답 여부는 알려주지 않은 채로" 재판단을 요청한다.
    -> 재생성된 SQL을 그제서야 gold와 비교해서 채점하고,
       4그룹(정상유지 / overcorrection / detection실패 / self-fixed)으로 분류한다.

이 파일은 src/ 폴더 안에 evaluate.py, pipeline.py, prompts.py와
나란히 두고 실행해야 함 (거기서 정의된 함수를 그대로 재사용하기 때문).

사용법:
    cd src
    python self_correct.py --predictions ../results/predictions_gpt-4o-mini_full500.json
"""

import json
import sqlite3
import argparse
from pathlib import Path
from collections import Counter

from dotenv import load_dotenv
from tqdm import tqdm

# 새로 안 짜고 기존 파일에 있던 함수를 그대로 가져와서 씀
from evaluate import is_correct   # (db_path, predicted_sql, gold_sql) -> True/False, 실행 결과 집합 비교
from pipeline import call_llm     # (prompt, model) -> LLM 호출 + SQL만 뽑아서 반환 (clean_sql 포함됨)

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_ROOT = ROOT / "data" / "mini_dev_data" / "dev_databases"
TARGET_DB = "toxicology"   # 이번 실험 대상 DB


def get_execution_feedback(db_path: str, sql: str, max_rows: int = 5):
    """
    predicted_sql을 '그냥 실행만' 해서, LLM에게 그대로 보여줄 피드백 텍스트를 만든다.

    핵심 포인트: 여기서는 정답 여부를 절대 판단하지 않는다.
    실제 서비스 환경에서 모델이 받을 수 있는 정보는 딱 이 정도뿐이기 때문
    (gold SQL은 애초에 존재하지 않음).

    Returns:
        (실행 성공 여부: bool, LLM에게 보여줄 피드백 문자열: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            # 실행은 됐지만 결과가 0건인 경우도 하나의 신호가 될 수 있어서 따로 표시
            return True, "쿼리는 정상적으로 실행됐지만, 결과가 0건입니다 (빈 결과)."

        preview = rows[:max_rows]
        feedback = (
            f"쿼리가 정상적으로 실행되어 {len(rows)}개의 row가 반환되었습니다.\n"
            f"결과 미리보기: {preview}"
        )
        return True, feedback

    except Exception as e:
        # evaluate.py의 execute_sql()은 에러가 나면 그냥 None을 반환해서
        # "실패했다"는 사실만 알 수 있음. 근데 우리는 "왜 실패했는지"를
        # LLM한테 피드백으로 그대로 넘겨줘야 해서, 여기서는 에러 메시지 자체를 잡아서 문자열로 만든다.
        error_text = f"{type(e).__name__}: {e}"
        return False, error_text


def build_self_correction_prompt(question: str, hint: str, predicted_sql: str, feedback: str) -> str:
    """
    재판단 요청 prompt를 만든다.

    ⚠️ 여기에 gold_sql은 절대 넣지 않는다.
    정답을 알려주면 "정답 주면 고치나요?" 실험이 되어버려서
    self-correction 실험의 의도(스스로 감지하는지 보는 것) 자체가 깨진다.
    """
    return f"""다음은 자연어 질문과, 그 질문에 대해 이미 생성된 SQL, 그리고 그 SQL을 실제로 실행한 결과입니다.

질문: {question}
힌트: {hint}

기존에 생성된 SQL:
{predicted_sql}

이 SQL을 실행한 결과:
{feedback}

이 실행 결과를 참고해서, SQL이 질문의 의도에 맞게 작성되었는지 판단하세요.
- 문제가 있다고 판단되면: 수정된 SQL만 반환하세요.
- 문제가 없다고 판단되면: 원래 SQL을 그대로 반환하세요.
설명 없이 SQL 쿼리만 반환하세요. 마크다운 포맷(```)도 쓰지 마세요."""


def classify(original_correct: bool, changed: bool, revised_correct: bool) -> str:
    """
    2x2 매트릭스 기준으로 4개(+예외 2개) 그룹으로 분류한다.
    (원래 정답/오답) x (모델이 SQL을 그대로 뒀는지 / 고쳤는지)
    """
    if original_correct and not changed:
        return "stable_correct"              # 왼쪽 위: 정상 유지
    if original_correct and changed:
        # 오른쪽 위: 맞던 걸 건드림 -> 여전히 맞으면 문제 없고, 틀려지면 overcorrection
        return "changed_but_still_correct" if revised_correct else "overcorrection_risk"
    if not original_correct and not changed:
        return "detection_failed"            # 왼쪽 아래: <- user interaction 필요 후보
    # not original_correct and changed
    return "self_fixed" if revised_correct else "changed_but_still_wrong"  # 오른쪽 아래


def run_self_correction(predictions_path: Path, db_root: Path, model: str = "gpt-4o-mini"):
    with open(predictions_path, "r") as f:
        all_predictions = json.load(f)

    # toxicology 문항만 필터링 (총 40개: 정답 19 + 오답 21, control group 포함)
    target_items = [d for d in all_predictions if d["db_id"] == TARGET_DB]
    print(f"{TARGET_DB} 대상 {len(target_items)}개 문항으로 진행")

    db_path = str(db_root / TARGET_DB / f"{TARGET_DB}.sqlite")
    results = []

    for item in tqdm(target_items, desc="Self-correction"):
        question = item["question"]
        hint = item.get("evidence", "")
        predicted_sql = item["predicted_sql"]
        gold_sql = item["gold_sql"]

        # 1. baseline이 원래 맞았는지 -- 이건 우리가(연구자가) 나중에 분류할 때 쓰려고
        #    미리 계산해두는 것뿐, LLM에게 넘기는 프롬프트에는 절대 들어가지 않는다.
        original_correct = is_correct(db_path, predicted_sql, gold_sql)

        # 2. SQL 실행 (gold 비교 없이 순수 실행만) -> 에러 메시지 or 결과 미리보기
        exec_success, feedback = get_execution_feedback(db_path, predicted_sql)

        # 3. 실행 결과를 붙여서 LLM에게 재판단 요청 (정답 여부는 안 알려줌)
        prompt = build_self_correction_prompt(question, hint, predicted_sql, feedback)
        try:
            revised_sql = call_llm(prompt, model)
        except Exception:
            revised_sql = predicted_sql  # API 호출 자체가 실패하면 원래 SQL 유지 (안전장치)

        # 4. 모델이 SQL을 실제로 바꿨는지 체크 (공백 차이는 무시)
        changed = revised_sql.strip() != predicted_sql.strip()

        # 5. 재채점 -- gold와 비교하는 건 여기가 '처음'이자 마지막
        revised_correct = is_correct(db_path, revised_sql, gold_sql)

        group = classify(original_correct, changed, revised_correct)

        results.append({
            "question_id": item["question_id"],
            "question": question,
            "evidence": hint,
            "predicted_sql": predicted_sql,
            "gold_sql": gold_sql,          # <- 비교용으로 추가함 (전엔 빠져있었음)
            "execution_success": exec_success,
            "execution_feedback": feedback,
            "revised_sql": revised_sql,
            "original_correct": original_correct,
            "changed": changed,
            "revised_correct": revised_correct,
            "group": group,
        })

    # 6. 결과 저장
    out_dir = ROOT / "results" / "self_correction"
    out_dir.mkdir(parents=True, exist_ok=True)

    full_path = out_dir / f"{TARGET_DB}_self_correction.json"
    with open(full_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # user interaction이 필요해 보이는 케이스(detection_failed)만 따로 로그로 저장
    # -> 나중에 "어떤 형식으로 피드백을 줘야 해결될지" 메모를 이 파일에 하나씩 추가해나가면 됨
    user_interaction_cases = [r for r in results if r["group"] == "detection_failed"]
    log_path = out_dir / "user_interaction_needed_log.json"
    with open(log_path, "w") as f:
        json.dump(user_interaction_cases, f, ensure_ascii=False, indent=2)

    print(f"\n전체 결과 저장: {full_path}")
    print(f"user interaction 로그: {log_path} ({len(user_interaction_cases)}개)")

    # 7. 결과 리포트 출력 (이전에는 별도 스크립트로 따로 돌렸던 부분을 여기로 합침)
    print_summary(results)
    print_fake_function_report(results)
    print_still_wrong_comparison(results)


def print_summary(results: list):
    """그룹별 개수 요약."""
    counts = Counter(r["group"] for r in results)
    print("\n=== 분류 결과 요약 ===")
    for group, count in counts.items():
        print(f"  {group}: {count}개")


def print_fake_function_report(results: list):
    """
    predicted_sql 안에 DIVIDE()/SUBTRACT()/MULTIPLY() 처럼
    hint의 pseudo-code를 SQL 함수로 착각한 케이스를 자동으로 찾아서
    (하드코딩된 qid 리스트 대신, 텍스트로 직접 탐지)
    각각 어느 그룹으로 분류됐는지 보여준다.
    """
    fake_funcs = ("DIVIDE(", "SUBTRACT(", "MULTIPLY(")
    print("\n=== DIVIDE/SUBTRACT/MULTIPLY 오사용 케이스 ===")
    for r in results:
        if any(f in r["predicted_sql"].upper() for f in fake_funcs):
            print(f"  qid {r['question_id']} -> {r['group']} | exec_success: {r['execution_success']}")


def print_still_wrong_comparison(results: list):
    """
    changed_but_still_wrong 그룹(고치긴 했는데 여전히 틀린 케이스)만 골라서
    질문 / 원래 SQL / 재생성 SQL / gold SQL을 나란히 출력한다.
    -> 왜 못 고쳤는지(새 실수를 만들었는지, 원래 있던 로직 에러를 못 잡았는지) 눈으로 확인하는 용도.
    """
    still_wrong = [r for r in results if r["group"] == "changed_but_still_wrong"]
    print(f"\n=== changed_but_still_wrong 상세 비교 ({len(still_wrong)}개) ===")
    for r in still_wrong:
        print(f"\n----- qid {r['question_id']} -----")
        print("질문:", r["question"])
        print("\n[원래 SQL]\n", r["predicted_sql"])
        print("\n[재생성 SQL]\n", r["revised_sql"])
        print("\n[gold SQL]\n", r["gold_sql"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predictions", type=Path,
        default=ROOT / "results" / "predictions_gpt-4o-mini_full500.json",
        help="baseline 결과 json 경로",
    )
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT, help="dev_databases 폴더 경로")
    parser.add_argument("--model", default="gpt-4o-mini", help="재판단에 쓸 모델")
    args = parser.parse_args()

    run_self_correction(args.predictions, args.db_root, args.model)
