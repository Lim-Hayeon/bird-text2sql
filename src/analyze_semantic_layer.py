"""
3-Condition 결과 비교 (raw / evidence / semlayer)

전제:
    run_semantic_layer_experiment.py 로 3개 조건의 predictions json을 만들고,
    각각 evaluate.py 로 채점(is_correct 필드 추가)까지 마친 상태여야 함:

    python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_raw.json
    python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_evidence.json
    python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_semlayer.json

사용법:
    python3 analyze_semantic_layer.py --model gpt-4o-mini
"""

import json
import argparse
from math import comb
from pathlib import Path
from itertools import combinations

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results" / "semantic_layer"

CONDITIONS = ["raw", "semlayer_a", "semlayer", "evidence"]  # Phase A만 -> Phase A+B -> oracle 순서로 배치

# self_correct.py 결과(toxicology_self_correction.json) 기준, held-out 27개 중
# 원래(raw, self-correction 이전) 정답/오답이었던 문항 -- 회귀/일반화 분석용.
# NOTE: 아래 리스트는 이전 self_correction 결과를 바탕으로 한 추정치이므로,
# 실제 toxicology_self_correction.json의 stable_correct / 그 외 그룹과
# 대조해서 정확히 맞는지 반드시 확인할 것.
ORIGINALLY_CORRECT = [195, 206, 208, 212, 213, 220, 226, 230, 232, 236, 240, 242, 243, 245, 249, 253, 255, 260, 268]
ORIGINALLY_WRONG = [201, 207, 215, 227, 228, 239, 282, 327]


def load_condition(model: str, condition: str) -> dict:
    """predictions_{model}_{condition}.json 을 로드해 {question_id: is_correct} dict로 반환."""
    path = RESULTS_DIR / f"predictions_{model}_{condition}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 가 없습니다. 먼저 run_semantic_layer_experiment.py --condition {condition} 를 실행하세요."
        )

    with open(path, "r") as f:
        data = json.load(f)

    result = {}
    for item in data:
        if "is_correct" not in item:
            raise KeyError(
                f"{path} 에 is_correct 필드가 없습니다. "
                f"먼저 evaluate.py --predictions {path} 로 채점을 완료하세요."
            )
        result[item["question_id"]] = item["is_correct"]
    return result


def pass_rate(results: dict) -> float:
    if not results:
        return 0.0
    return sum(results.values()) / len(results) * 100


def mcnemar_table(results_a: dict, results_b: dict):
    """두 조건 간 discordant pair 계산. b = a만 맞음, c = b만 맞음."""
    common_ids = set(results_a.keys()) & set(results_b.keys())
    b = c = 0
    for qid in common_ids:
        a_correct = results_a[qid]
        b_correct = results_b[qid]
        if a_correct and not b_correct:
            b += 1
        elif (not a_correct) and b_correct:
            c += 1
    return b, c


def exact_mcnemar_pvalue(b: int, c: int) -> float:
    """Two-sided exact McNemar test (binomial 기반, scipy/statsmodels 의존성 없이 계산)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p_le_k = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * p_le_k)


def regression_and_generalization(semlayer_results: dict):
    """
    회귀(regression): 원래 정답이었는데 semlayer 조건에서 틀린 문항
    일반화(generalization): 원래 오답이었는데 semlayer 조건에서 새로 맞은 문항
    """
    regression = [qid for qid in ORIGINALLY_CORRECT if qid in semlayer_results and not semlayer_results[qid]]
    generalized = [qid for qid in ORIGINALLY_WRONG if qid in semlayer_results and semlayer_results[qid]]
    return regression, generalized


def run_analysis(model: str):
    results = {cond: load_condition(model, cond) for cond in CONDITIONS}

    print(f"=== {model} — Pass Rate by Condition (n={len(results['raw'])}) ===")
    for cond in CONDITIONS:
        n_correct = sum(results[cond].values())
        n_total = len(results[cond])
        print(f"  {cond:10s}: {pass_rate(results[cond]):5.1f}%  ({n_correct}/{n_total})")

    print(f"\n=== Pairwise McNemar (two-sided exact) ===")
    for cond_a, cond_b in combinations(CONDITIONS, 2):
        b, c = mcnemar_table(results[cond_a], results[cond_b])
        p = exact_mcnemar_pvalue(b, c)
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
        print(f"  {cond_a:10s} vs {cond_b:10s}: b={b:2d} (only {cond_a} correct), "
              f"c={c:2d} (only {cond_b} correct), p={p:.4f} {sig}")

    print(f"\n=== 회귀 / 일반화 분석 (raw 대비 semlayer) ===")
    regression, generalized = regression_and_generalization(results["semlayer"])
    print(f"  회귀 (원래 맞았는데 semlayer에서 틀림)  : {regression if regression else '없음'}")
    print(f"  일반화 (원래 틀렸는데 semlayer에서 맞음): {generalized if generalized else '없음'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()

    run_analysis(args.model)