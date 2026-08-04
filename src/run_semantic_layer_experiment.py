"""
Semantic Layer 3-Condition 실험 (toxicology DB, held-out 27문항)

목적:
    같은 질문에 대해 세 조건으로만 프롬프트를 바꿔서 LLM에게 SQL을 생성시키고,
    조건 간 정확도를 비교한다. (Contoso 논문의 paired-comparison 설계를 따름)

    A. raw       : 스키마만 제공 (hint 없음)
    B. evidence  : 스키마 + BIRD 원본 evidence(hint) 제공 (기존 pipeline.py와 동일)
    C. semlayer  : 스키마 + runbooks/{db_id}_runbook.md 제공 (evidence는 안 줌)

    세 조건 모두 질문 세트·모델·temperature·prompt 조립 방식은 동일하게 유지하고,
    "무엇을 컨텍스트로 주는지"만 바꾼다.

전제:
    - runbooks/toxicology_runbook.md 가 이미 존재해야 함
    - data/mini_dev_data/mini_dev_sqlite.json, dev_databases/ 가 이미 있어야 함
    - held-out 문항 리스트는 runbook의 "Build / Held-out 문항 분리" 섹션과
      반드시 일치해야 함 (build set 문항을 여기서 실수로 돌리면 leakage 발생)

사용법:
    cd src
    python3 run_semantic_layer_experiment.py --model gpt-4o-mini --condition raw
    python3 run_semantic_layer_experiment.py --model gpt-4o-mini --condition evidence
    python3 run_semantic_layer_experiment.py --model gpt-4o-mini --condition semlayer

    # 채점은 기존 evaluate.py 그대로 재사용
    python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_semlayer.json
"""

import os
import json
import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from prompts import get_schema_text

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEV_JSON = ROOT / "data" / "mini_dev_data" / "mini_dev_sqlite.json"
DEFAULT_DB_ROOT = ROOT / "data" / "mini_dev_data" / "dev_databases"
RUNBOOK_DIR = ROOT / "runbooks"
OUTPUT_DIR = ROOT / "results" / "semantic_layer"

DB_ID = "toxicology"

# runbook의 "Held-out test set (27개)" 리스트 (build set 10개는 절대 포함하지 않음)
HELD_OUT_QUESTION_IDS = [
    195, 201, 206, 207, 208, 212, 213, 215, 220, 226,
    227, 228, 230, 232, 236, 239, 240, 242, 243, 245,
    249, 253, 255, 260, 268, 282, 327,
]

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


RUNBOOK_FILENAME_BY_CONDITION = {
    "semlayer": "{db_id}_runbook.md",                # Phase A + Phase B 결합본
    "semlayer_a": "{db_id}_runbook_phaseA_only.md",   # Phase A만 (ablation)
}


def load_runbook_text(db_id: str, condition: str) -> str:
    """runbooks/ 안의 조건별 런북 파일을 읽어서, Appendix(메타정보) 이전까지만 반환."""
    filename = RUNBOOK_FILENAME_BY_CONDITION[condition].format(db_id=db_id)
    runbook_path = RUNBOOK_DIR / filename
    with open(runbook_path, "r", encoding="utf-8") as f:
        content = f.read()

    # "## Appendix"부터는 문서 검증 노트 / 규칙-오답 매핑표 / build-held-out 분리 목록 등
    # 모델에게 줄 필요 없는 메타정보이므로, 그 앞부분(섹션 목록)까지만 잘라서 사용한다.
    core_content = content.split("## Appendix")[0].strip()
    return core_content


def build_prompt(question: str, schema_text: str, condition: str, hint: str = "", runbook_text: str = "") -> str:
    instruction = (
        "\n\nPlease write the SQL query.\n"
        "Return ONLY the SQL query, with no explanation and no markdown formatting."
    )

    if condition == "raw":
        return f"Question: {question}\n\nSchema:\n{schema_text}{instruction}"

    elif condition == "evidence":
        hint_section = f"\n\nHint:\n{hint}" if hint else ""
        return f"Question: {question}\n\nSchema:\n{schema_text}{hint_section}{instruction}"

    elif condition in ("semlayer", "semlayer_a"):
        # semlayer      = Phase A + Phase B 결합 런북
        # semlayer_a    = Phase A만 남긴 ablation 런북 (Phase B의 추가 기여도 측정용)
        semlayer_section = (
            f"\n\nSemantic Layer (domain knowledge, business rules):\n{runbook_text}"
            if runbook_text else ""
        )
        return f"Question: {question}\n\nSchema:\n{schema_text}{semlayer_section}{instruction}"

    else:
        raise ValueError(f"알 수 없는 condition: {condition}")


def clean_sql(raw_output: str) -> str:
    raw_output = raw_output.replace("```sql", "").replace("```", "")
    return raw_output.strip()


def call_llm(prompt: str, model: str) -> str:
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 2000,
    }
    if not model.startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["temperature"] = 0.0

    response = client.chat.completions.create(**kwargs)
    return clean_sql(response.choices[0].message.content)


def run_experiment(model: str, condition: str, dev_json: Path, db_root: Path):
    with open(dev_json, "r") as f:
        data = json.load(f)

    filtered = [
        d for d in data
        if d.get("db_id") == DB_ID and d.get("question_id") in HELD_OUT_QUESTION_IDS
    ]

    if len(filtered) != len(HELD_OUT_QUESTION_IDS):
        print(f"경고: held-out {len(HELD_OUT_QUESTION_IDS)}개 중 {len(filtered)}개만 매칭됨. "
              f"question_id 오타나 db_id 불일치 확인 필요")

    runbook_text = load_runbook_text(DB_ID, condition) if condition in ("semlayer", "semlayer_a") else ""

    predictions = []

    for item in tqdm(filtered, desc=f"{model} / {condition}"):
        question = item["question"]
        hint = item.get("evidence", "")
        question_id = item.get("question_id")

        db_path = db_root / DB_ID / f"{DB_ID}.sqlite"
        schema_text = get_schema_text(str(db_path))
        prompt = build_prompt(question, schema_text, condition, hint=hint, runbook_text=runbook_text)

        try:
            predicted_sql = call_llm(prompt, model)
        except Exception as e:
            predicted_sql = f"ERROR: {e}"

        predictions.append({
            "question_id": question_id,
            "db_id": DB_ID,
            "question": question,
            "condition": condition,
            "evidence": hint,
            "gold_sql": item.get("SQL", ""),
            "predicted_sql": predicted_sql,
            "model": model,
        })

    safe_model_name = model.replace("/", "_")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"predictions_{safe_model_name}_{condition}.json"
    with open(output_path, "w") as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)

    print(f"\n저장 완료: {output_path} ({len(predictions)}개)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--condition", required=True, choices=["raw", "evidence", "semlayer", "semlayer_a"])
    parser.add_argument("--dev-json", type=Path, default=DEFAULT_DEV_JSON)
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT)
    args = parser.parse_args()

    run_experiment(
        model=args.model,
        condition=args.condition,
        dev_json=args.dev_json,
        db_root=args.db_root,
    )