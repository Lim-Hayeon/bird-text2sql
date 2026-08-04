"""
Feedback 로그 생성

목적:
    clarification_experiment.json (A/B/C 실험 원본 데이터)은 실험 기록일 뿐,
    "나중에 비슷한 질문이 왔을 때 참고할 수 있는 형태"는 아니었음.

    이 스크립트는 그 원본 데이터에
    - 카테고리 태그 (출력형식 / 의도모호 / 도메인지식 / 벤치마크이슈)
    - 실제로 통했던 최소 개입 단계와 그 문구
    - 원본 SQL (baseline)
    를 합쳐서, 진짜로 "참고 가능한" feedback_log.json을 만든다.

전제:
    self_correct.py, clarification_experiment.py를 먼저 돌려서
    results/self_correction/ 안에
    - user_interaction_needed_log.json (원본 predicted_sql, evidence 포함)
    - toxicology_clarification_experiment.json (A/B/C 시도 결과)
    두 파일이 이미 있어야 함.

사용법:
    cd src
    python3 build_feedback_log.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF_CORRECTION_DIR = ROOT / "results" / "self_correction"

# qid별 카테고리 태그 (사수님 미팅 + 분석 과정에서 정리한 것 그대로 재사용)
CATEGORY = {
    200: "출력형식", 231: "출력형식", 327: "출력형식",
    207: "의도모호", 215: "의도모호", 218: "의도모호",
    197: "도메인지식", 281: "도메인지식", 248: "도메인지식",
    234: "벤치마크이슈",
}

# C까지 줘도 안 풀린 3개는, 왜 안 풀렸는지 SQL을 직접 뜯어보고 확인한 내용을 수기로 남겨둠.
# (이건 자동으로 판단 못 하는 부분이라 분석하면서 확인한 결론을 그대로 기록)
FAILURE_NOTES = {
    207: "clarification 자체는 정확히 반영됨(DISTINCT 추가). 다만 SELECT 절에서 결합 반대쪽 원자(a2.element)가 누락됨 -- 개념 이해는 맞았으나 구현 단계에서 누락 발생.",
    234: "gold_sql이 질문의 조건(atom 12)과 무관한 하드코딩(_1/_2)을 사용함. clarification을 아무리 줘도 모델이 더 합리적인 해석을 내놓기 때문에 원천적으로 해결 불가 -- BIRD gold annotation 오류로 추정.",
    248: "개념(triple bond = 원자 두 개)은 정확히 이해했으나, 존재하지 않는 컬럼(atom_id1)을 추측해서 사용 -- 실행 시 'no such column' 에러로 확인됨. clarification은 유효했지만 스키마 정확도 부족으로 실패.",
}


def build_feedback_log():
    with open(SELF_CORRECTION_DIR / "user_interaction_needed_log.json", "r") as f:
        original_cases = json.load(f)
    with open(SELF_CORRECTION_DIR / "toxicology_clarification_experiment.json", "r") as f:
        clarification_results = json.load(f)

    # question_id로 두 파일을 합치기 위해, 원본 케이스를 dict로 인덱싱해둠
    original_by_qid = {c["question_id"]: c for c in original_cases}

    feedback_log = []

    for r in clarification_results:
        qid = r["question_id"]
        original = original_by_qid.get(qid, {})
        level = r["min_level_success"]  # 성공했으면 "A"/"B"/"C", 실패면 None

        entry = {
            "question_id": qid,
            "question": r["question"],
            "category": CATEGORY.get(qid, "미분류"),
            "resolved": level is not None,
            "original_sql": original.get("predicted_sql"),
            "gold_sql": r["gold_sql"],
        }

        if level is not None:
            # 성공한 경우: 실제로 통했던 최소 개입 단계의 문구와 결과 SQL을 기록
            # -> 이게 "나중에 참고할" 핵심 정보 (비슷한 유형 질문에 이 정도 개입이면 충분하다는 근거)
            entry["clarification_level_used"] = level
            entry["clarification_text"] = r["formats"][level]["clarification"]
            entry["resolved_sql"] = r["formats"][level]["revised_sql"]
        else:
            # 실패한 경우: A/B/C 문구를 전부 남겨서 "이 정도까지 줘봤는데도 안 됐다"를 기록해두고,
            # 수기로 분석한 실패 원인도 같이 붙여둔다.
            entry["clarification_level_used"] = None
            entry["all_attempts"] = {
                lvl: r["formats"][lvl]["clarification"] for lvl in ("A", "B", "C")
            }
            entry["failure_reason"] = FAILURE_NOTES.get(qid, "미분석")

        feedback_log.append(entry)

    out_path = SELF_CORRECTION_DIR / "feedback_log.json"
    with open(out_path, "w") as f:
        json.dump(feedback_log, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {out_path}")
    print_summary(feedback_log)


def print_summary(feedback_log: list):
    resolved = [e for e in feedback_log if e["resolved"]]
    unresolved = [e for e in feedback_log if not e["resolved"]]

    print(f"\n총 {len(feedback_log)}개 중 해결 {len(resolved)}개 / 미해결 {len(unresolved)}개")

    print("\n=== 카테고리별 해결 현황 ===")
    categories = sorted(set(e["category"] for e in feedback_log))
    for cat in categories:
        cat_entries = [e for e in feedback_log if e["category"] == cat]
        cat_resolved = [e for e in cat_entries if e["resolved"]]
        levels = [e["clarification_level_used"] for e in cat_resolved]
        print(f"  {cat}: {len(cat_resolved)}/{len(cat_entries)} 해결, 사용된 단계: {levels}")

    print("\n=== 미해결 케이스 사유 ===")
    for e in unresolved:
        print(f"  qid {e['question_id']}: {e['failure_reason']}")


if __name__ == "__main__":
    build_feedback_log()
