"""
Clarification 형식 비교 실험

목적:
    detection_failed 10개 케이스에 대해, 사용자 개입을 3가지 강도로 나눠서
    (A: 정보만 제공 / B: 질문 재진술 / C: 직접 지시) 각각 시도해보고
    "어느 정도의 개입부터 모델이 알아듣는지" 최소 개입 지점을 찾는다.

    ⚠️ 세 형식 모두 gold_sql을 그대로 알려주지는 않는다.
    실제 사용자가 자연스럽게 줄 법한 정보/질문/지시 수준으로만 구성함.

전제:
    self_correct.py를 먼저 돌려서
    results/self_correction/user_interaction_needed_log.json 이 만들어져 있어야 함
    (거기에 question, evidence, predicted_sql, execution_feedback, gold_sql이 이미 들어있어서
    이번 스크립트에서는 새로 실행/계산할 필요 없이 그대로 재사용함)

사용법:
    cd src
    python3 clarification_experiment.py
"""

import json
from pathlib import Path
from collections import Counter

from dotenv import load_dotenv
from tqdm import tqdm

from evaluate import is_correct   # 기존 파일 재사용
from pipeline import call_llm     # 기존 파일 재사용

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_ROOT = ROOT / "data" / "mini_dev_data" / "dev_databases"
TARGET_DB = "toxicology"

# qid별로 미리 설계해둔 3단계 clarification.
# A: 정보만 제공 (정답/의도 암시 없음)
# B: 질문 재진술 (모델이 놓쳤을 법한 해석의 갈림길을 되물어봄)
# C: 직접 지시 (뭘 해야 하는지 구체적으로 지시, 단 gold_sql 자체는 아님)
CLARIFICATIONS = {
    197: {
        "A": "이 DB에서 atom과 bond는 둘 다 molecule_id 컬럼을 가지고 있습니다.",
        "B": "atom과 bond를 연결할 때, connected 테이블을 거쳐야 하나요, 아니면 둘 다 가진 molecule_id로 바로 연결해도 되나요?",
        "C": "connected 테이블 없이, atom과 bond를 molecule_id로 직접 조인해서 계산해주세요.",
    },
    200: {
        "A": "carcinogenic 여부는 이미 조건절에 있습니다.",
        "B": "결과에 분자 ID만 필요한가요, 아니면 label 값도 같이 보여줘야 하나요?",
        "C": "molecule_id만 반환해주세요, label은 빼주세요.",
    },
    207: {
        "A": "결합은 두 원자를 연결합니다. 원소 종류 자체는 몇 가지 안 됩니다 (c, o, h, n 등).",
        "B": "결합에 참여하는 원소를 '쌍'으로 나열하길 원하시나요, 아니면 등장하는 원소의 '종류 목록'을 원하시나요?",
        "C": "쌍이 아니라, 중복 없이 원소 종류만 하나의 리스트로 반환해주세요.",
    },
    215: {
        "A": "iodine과 sulfur는 서로 다른 원소입니다.",
        "B": "iodine 개수와 sulfur 개수를 하나로 합친 값을 원하시나요, 아니면 각각 따로 알고 싶으신가요?",
        "C": "두 원소의 개수를 각각 별도의 컬럼으로 따로 반환해주세요.",
    },
    218: {
        "A": "한 분자 안에 여러 개의 원자가 있을 수 있습니다.",
        "B": "'불소를 포함하지 않는다'는 게, 그 분자의 모든 원자가 불소가 아니라는 뜻인가요, 아니면 불소가 아닌 원자가 하나라도 있으면 되는 건가요?",
        "C": "분자 안에 불소 원자가 하나도 없는 경우만 '포함 안 함'으로 계산해주세요.",
    },
    231: {
        "A": "질문은 bond_type이 무엇인지만 묻고 있습니다.",
        "B": "결과에 개수(count)도 같이 보여줘야 하나요, 아니면 bond_type 값만 필요한가요?",
        "C": "bond_type 컬럼만 반환해주세요, count는 빼주세요.",
    },
    234: {
        "A": "atom_id는 'TR009_12'처럼 분자ID_원자번호 형식입니다.",
        "B": "atom_id 컬럼과 atom_id2 컬럼 중 하나라도 일치하면 되는 건가요?",
        "C": "hint에 나온 조건 그대로 다시 한 번 확인해서 작성해주세요.",
    },
    248: {
        "A": "bond 테이블의 한 row는 두 원자 사이의 결합 하나를 의미합니다.",
        "B": "'triple bond의 원자들'이 세 개의 원자를 찾으라는 뜻인가요, 아니면 그 결합에 참여하는 두 원자를 찾으라는 뜻인가요?",
        "C": "triple bond는 원자 두 개 사이의 결합입니다. 그 결합에 연결된 두 원자만 반환해주세요.",
    },
    281: {
        "A": "atom_id의 길이는 분자마다 다를 수 있습니다 (원자가 10개 넘는 분자도 있음).",
        "B": "atom_id의 특정 위치(7번째 글자)를 보는 게 맞나요, 아니면 원자 번호가 항상 마지막 자리에 오는 걸 기준으로 봐야 하나요?",
        "C": "atom_id 뒤에서부터 세어서 마지막 글자가 '4'인 것만 찾아주세요. 단, 전체 길이가 7자리인 것만 (두 자리 번호는 제외).",
    },
    327: {
        "A": "label 값은 이미 조건절(WHERE label = '-')에 사용되고 있습니다.",
        "B": "결과에 label도 같이 보여줘야 하나요, molecule_id만 있으면 되나요?",
        "C": "molecule_id만 반환해주세요, label은 빼주세요.",
    },
}


def build_clarified_prompt(question: str, hint: str, predicted_sql: str, feedback: str, clarification: str) -> str:
    """
    self_correct.py의 build_self_correction_prompt에 '사용자 설명' 섹션만 추가한 버전.
    이 섹션 하나만 A/B/C로 바뀌고 나머지 구조는 동일하게 유지해서,
    형식 차이 외의 변수를 최대한 통제한다.
    """
    return f"""다음은 자연어 질문과, 그 질문에 대해 이미 생성된 SQL, 그 SQL을 실행한 결과,
그리고 사용자가 추가로 제공한 설명입니다.

질문: {question}
힌트: {hint}

기존에 생성된 SQL:
{predicted_sql}

이 SQL을 실행한 결과:
{feedback}

사용자 설명:
{clarification}

위 사용자 설명을 참고해서 SQL을 수정하세요.
설명 없이 SQL 쿼리만 반환하세요. 마크다운 포맷(```)도 쓰지 마세요."""


def run_clarification_experiment(log_path: Path, db_root: Path, model: str = "gpt-4o-mini"):
    with open(log_path, "r") as f:
        cases = json.load(f)

    db_path = str(db_root / TARGET_DB / f"{TARGET_DB}.sqlite")
    results = []

    for item in tqdm(cases, desc="Clarification 실험"):
        qid = item["question_id"]

        # CLARIFICATIONS에 미리 준비 안 해둔 qid가 섞여 있으면 건너뜀 (안전장치)
        if qid not in CLARIFICATIONS:
            continue

        row = {
            "question_id": qid,
            "question": item["question"],
            "gold_sql": item["gold_sql"],
            "formats": {},
        }

        # A -> B -> C 순서로 각각 "독립적으로" 시도한다.
        # (B를 시도할 때 A의 결과를 이어받지 않고, 매번 원래 predicted_sql에서 새로 시작함
        #  -> 그래야 "이 형식 하나만으로 충분한가"를 순수하게 비교할 수 있음)
        for level in ("A", "B", "C"):
            clarification = CLARIFICATIONS[qid][level]
            prompt = build_clarified_prompt(
                item["question"], item["evidence"], item["predicted_sql"],
                item["execution_feedback"], clarification,
            )
            try:
                revised_sql = call_llm(prompt, model)
            except Exception:
                revised_sql = item["predicted_sql"]  # 호출 실패 시 안전장치

            correct = is_correct(db_path, revised_sql, item["gold_sql"])

            row["formats"][level] = {
                "clarification": clarification,
                "revised_sql": revised_sql,
                "correct": correct,
            }

        # 이 케이스에서 "최소 개입으로 성공한 단계"를 기록 (A가 제일 약한 개입)
        row["min_level_success"] = next(
            (lvl for lvl in ("A", "B", "C") if row["formats"][lvl]["correct"]), None
        )

        results.append(row)

    # 결과 저장
    out_path = ROOT / "results" / "self_correction" / f"{TARGET_DB}_clarification_experiment.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n저장 완료: {out_path}")
    print_report(results)


def print_report(results: list):
    n = len(results)

    # 형식별 성공률 (각 형식은 서로 독립 시도이므로, 단순히 성공 개수를 셈)
    print("\n=== 형식별 성공 개수 (10개 케이스 각각 독립 시도) ===")
    for level in ("A", "B", "C"):
        success = sum(1 for r in results if r["formats"][level]["correct"])
        print(f"  {level}: {success}/{n}")

    # 케이스별 최소 개입 지점
    print("\n=== 케이스별 최소 개입 지점 ===")
    for r in results:
        level = r["min_level_success"] or "실패 (A/B/C 모두 안 됨)"
        print(f"  qid {r['question_id']}: {level}")

    # 전체 요약 (아예 안 풀린 케이스가 몇 개인지)
    unresolved = [r["question_id"] for r in results if r["min_level_success"] is None]
    print(f"\nA/B/C 세 형식 다 시도해도 안 풀린 케이스: {unresolved}")


if __name__ == "__main__":
    log_path = ROOT / "results" / "self_correction" / "user_interaction_needed_log.json"
    run_clarification_experiment(log_path, DEFAULT_DB_ROOT)
