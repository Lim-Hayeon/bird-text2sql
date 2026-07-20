# 🐦 BIRD Mini-Dev Text-to-SQL Baseline

Natural Language Question → SQL 변환 파이프라인. [BIRD Mini-Dev](https://bird-bench.github.io/) 벤치마크 기준으로 gpt-4o-mini의 baseline 성능을 측정하고, 오답 케이스를 분석한 프로젝트입니다.

## 📊 Results

| Metric | Value |
|---|---|
| **EX (Execution Accuracy)** | **41.40%** (207/500) |
| Model | gpt-4o-mini |
| Dataset | BIRD Mini-Dev (SQLite), 500 questions |

<details>
<summary>공식 리더보드와 비교 (SQLite 기준)</summary>

| Model | EX (%) |
|---|---|
| gpt-3.5-turbo | 38.00 |
| **gpt-4o-mini (this repo)** | **41.40** |
| gpt-4-turbo | 45.80 |
| gpt-4 | 47.80 |

</details>

### Hard 문항 비교: gpt-4o-mini vs gpt-5.5

동일한 challenging 난이도 20문항으로 비교:

| Model | EX |
|---|---|
| gpt-4o-mini | 10.00% (2/20) |
| gpt-5.5 | 30.00% (6/20) |

## 🔧 Pipeline
NLQ (question) + Schema (CREATE TABLE) + Hint (evidence)
│
▼
gpt-4o-mini
│
▼
SQL

스키마는 SQLite의 `sqlite_master`에서 원본 `CREATE TABLE` 문을 그대로 추출해 사용합니다. 평가는 문자열 비교가 아닌 **실행 결과 비교(EX)** 방식을 사용합니다 — predicted SQL과 gold SQL을 각각 실행해 결과 집합이 일치하는지 확인합니다.

## 📁 Project Structure
```
bird-text2sql/
├── src/
│   ├── prompts.py      # Schema 추출 + Prompt 조립
│   ├── pipeline.py      # LLM 호출 → SQL 생성
│   └── evaluate.py      # EX 계산 + 오답 케이스 추출
├── data/
│   └── mini_dev_data/    # BIRD Mini-Dev 데이터셋
└── results/
├── predictions_*.json
└── error_analysis/
└── wrong_cases.json
```

## 🚀 Usage

```bash
# 의존성 설치
pip install -r requirements.txt

# .env에 API key 설정
cp .env.example .env

# 파이프라인 실행
python3 src/pipeline.py --model gpt-4o-mini

# 채점
python3 src/evaluate.py --predictions results/predictions_gpt-4o-mini.json
```

**옵션**
- `--limit N` : 앞에서 N개 문항만 실행 (테스트용)
- `--hard-only` : challenging 난이도만 실행

## 🔍 Error Analysis

오답 293개를 4개 카테고리로 분류:

| Category | Count | % |
|---|---|---|
| ① Hint 의사코드를 SQL 함수로 오인 (`DIVIDE()`, `SUBTRACT()` 등) | 30 | 10.2% |
| ② 출력 컬럼 구성 불일치 | 117 | 39.9% |
| ③ 로직/계산 오류 | 121 | 41.3% |
| ④ 실행 실패 (타임아웃, 멀티 스테이트먼트 등) | 25 | 8.5% |

가장 큰 실패 원인은 **출력 형식 불일치(40%)** — 모델이 질문의 로직 자체는 상당 부분 맞게 이해하지만, 정확히 어떤 컬럼만 반환해야 하는지를 지키지 못하는 경향이 확인되었습니다.

## 🔮 Future Work

- Few-shot 예시를 통한 출력 형식 정확도 개선
- Self-correction 루프 도입 (실행 에러 발생 시 LLM에 피드백 후 재생성) — 카테고리 ①·④(전체 오답의 약 19%)는 이 방식으로 개선 가능성이 높아 보임
- LangGraph 기반 multi-step pipeline으로 확장

## 🛠 Tech Stack

Python · OpenAI API (gpt-4o-mini, gpt-5.5) · SQLite
