# 🐦 BIRD Mini-Dev Text-to-SQL Baseline

Natural Language Question → SQL 변환 파이프라인. [BIRD Mini-Dev](https://bird-bench.github.io/) 벤치마크 기준으로 gpt-4o-mini의 baseline 성능을 측정하고, 오답 케이스를 분석한 프로젝트입니다. 이후 toxicology DB를 대상으로 **self-correction(실행 피드백만으로 스스로 에러를 잡아낼 수 있는지)**, **user interaction 형식 비교(어떤 개입이면 모델이 알아듣는지)**, 그리고 **semantic layer 런북 파일럿(도메인 지식을 사전에 명시하면 모호성이 줄어드는지)** 실험까지 진행했습니다.

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
├── runbooks/
│ ├── toxicology_runbook.md # Semantic layer 런북 (Phase A + Phase B 결합)
│ └── toxicology_runbook_phaseA_only.md # Phase A만 남긴 ablation용 런북
├── src/
│ ├── prompts.py # Schema 추출 + Prompt 조립
│ ├── pipeline.py # LLM 호출 → SQL 생성
│ ├── evaluate.py # EX 계산 + 오답 케이스 추출
│ ├── self_correct.py # 실행 결과 피드백만으로 self-correction 시도
│ ├── clarification_experiment.py # A/B/C 형식별 user interaction 비교 실험
│ ├── check_detection_failed.py # detection_failed 케이스 재확인용 헬퍼
│ ├── check_near_miss.py # 부동소수점 near-miss 오답 검증
│ ├── build_feedback_log.py # user interaction 결과를 참고 가능한 로그로 정리
│ ├── run_semantic_layer_experiment.py # raw/evidence/semlayer/semlayer_a 4-condition 실험
│ └── analyze_semantic_layer.py # 4-condition 결과 비교 + McNemar 검정
├── data/
│ └── mini_dev_data/ # BIRD Mini-Dev 데이터셋
└── results/
├── predictions_*.json
├── error_analysis/
│ └── wrong_cases.json
├── self_correction/
│ ├── toxicology_self_correction.json # self-correction 실험 전체 결과
│ ├── user_interaction_needed_log.json # user interaction 필요 후보 (detection_failed)
│ ├── toxicology_clarification_experiment.json # A/B/C 형식 비교 실험 전체 결과
│ └── feedback_log.json # 카테고리별 정리된 최종 참고 로그
└── semantic_layer/
├── predictions_gpt-4o-mini_{raw,evidence,semlayer,semlayer_a}.json
└── wrong_cases_{raw,evidence,semlayer,semlayer_a}.json
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

### Self-correction & Clarification 실험 실행

```bash
cd src

# 1. baseline SQL을 gold와 비교 없이 실행 → 실행 결과만 피드백으로 재판단 요청
python3 self_correct.py

# 2. detection_failed 케이스에 A(정보 제공)/B(질문 재진술)/C(직접 지시) 형식 비교
python3 clarification_experiment.py

# 3. 결과를 카테고리별 참고 로그로 정리
python3 build_feedback_log.py
```

### Semantic Layer 파일럿 실험 실행

```bash
cd src

# 4개 조건(raw/evidence/semlayer/semlayer_a) 각각 실행
python3 run_semantic_layer_experiment.py --model gpt-4o-mini --condition raw
python3 run_semantic_layer_experiment.py --model gpt-4o-mini --condition evidence
python3 run_semantic_layer_experiment.py --model gpt-4o-mini --condition semlayer
python3 run_semantic_layer_experiment.py --model gpt-4o-mini --condition semlayer_a

# 채점
python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_raw.json
python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_evidence.json
python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_semlayer.json
python3 evaluate.py --predictions ../results/semantic_layer/predictions_gpt-4o-mini_semlayer_a.json

# 4-condition 비교 분석
python3 analyze_semantic_layer.py --model gpt-4o-mini
```

## 🔍 Error Analysis

오답 293개를 4개 카테고리로 분류:

| Category | Count | % |
|---|---|---|
| ① Hint 의사코드를 SQL 함수로 오인 (`DIVIDE()`, `SUBTRACT()` 등) | 30 | 10.2% |
| ② 출력 컬럼 구성 불일치 | 117 | 39.9% |
| ③ 로직/계산 오류 | 121 | 41.3% |
| ④ 실행 실패 (타임아웃, 멀티 스테이트먼트 등) | 25 | 8.5% |

가장 큰 실패 원인은 **출력 형식 불일치(40%)** — 모델이 질문의 로직 자체는 상당 부분 맞게 이해하지만, 정확히 어떤 컬럼만 반환해야 하는지를 지키지 못하는 경향이 확인되었습니다.

## 🔁 Self-Correction 실험 (toxicology DB)

Future Work로 남겨뒀던 "실행 에러 발생 시 LLM에 피드백 후 재생성"을 실제로 구현하고 검증했습니다. toxicology DB 40문항(baseline 정답 19 / 오답 21) 전체를 대상으로, gold SQL과 비교하지 않고 baseline predicted_sql을 **그냥 실행만** 해본 뒤, 그 실행 결과(에러 메시지 또는 결과 row)만 LLM에게 다시 보여주고 **정답 여부는 알려주지 않은 채** 재판단을 요청했습니다.

### 결과

| 그룹 | 개수 | 의미 |
|---|---|---|
| stable_correct | 19 | 원래 정답, 건드리지 않고 유지 |
| overcorrection_risk | 0 | 원래 정답인데 잘못 고쳐서 틀려진 경우 — 0건 (부작용 없음) |
| detection_failed | 10 | 실행 결과를 줘도 문제를 전혀 인지 못 함 → user interaction 필요 |
| self_fixed | 4 | 실행 결과만으로 스스로 감지하고 정확히 고침 |
| changed_but_still_wrong | 7 | 문제를 감지하고 수정을 시도했지만 여전히 틀림 |

### 핵심 발견

- **명시적 실행 에러**(`no such function: DIVIDE` 등, 8건)는 "문제 인지"까지는 100% 보장하지만 "정확한 수정"은 보장하지 않음. 문법 에러와 로직 에러가 한 쿼리에 섞여 있으면, 모델은 눈에 보이는 문법만 고치고 로직 문제는 놓침 (self_fixed 3건 vs changed_but_still_wrong 5건). 심지어 에러 원인 자체를 오진단하는 경우도 확인됨 (qid 273).
- **실행 에러가 없어도**, 결과값 자체가 상식적으로 이상하면(0건 등) 드물게 감지 가능함 (qid 239, `=` 연산자를 `LIKE`로 스스로 수정). 하지만 결과가 "그럴듯하게" 보이는 순간 감지 확률은 급격히 낮아짐 (10/13 실패).

## 💬 User Interaction 형식 비교 실험

detection_failed 10건을 대상으로, "어떤 형식으로 개입해야 모델이 알아듣는지"를 3단계로 나눠 비교했습니다.

| 형식 | 설명 |
|---|---|
| A. 정보만 제공 | 정답/의도를 암시하지 않고 스키마·데이터 사실만 제공 |
| B. 질문 재진술 | 해석이 갈리는 지점을 질문 형태로 되물음 |
| C. 직접 지시 | 구체적으로 지시하되 gold SQL 자체는 알려주지 않음 |

### 결과

| 형식 | 성공 (10개 중) |
|---|---|
| A | 2 |
| B | 4 |
| C | 7 |

성공 케이스가 **A ⊂ B ⊂ C** 완전 누적 구조로 나타나, 개입 강도와 성공률이 단조 증가함을 확인했습니다. 문제 유형별로 필요한 최소 개입 강도도 다르게 나타났습니다 — 출력 형식 문제(3/3)는 가벼운 개입(A·A·B)만으로 해결된 반면, 의도 모호·도메인 지식 문제는 B/C 수준의 개입이 필요했습니다.

C까지 줘도 실패한 3건 중 실질적으로 "해결 불가능"한 경우는 gold annotation 오류로 추정되는 1건뿐이었고, 나머지 2건은 clarification 자체는 올바르게 작동했으나 모델이 구현 과정에서 별개의 새로운 실수(컬럼 누락, 존재하지 않는 컬럼 추측)를 만들어낸 경우였습니다.

이 실험에서 나온 detection_failed 10건의 카테고리·해결 이력은 `build_feedback_log.py`를 통해 `feedback_log.json`으로 정리되어, 이후 유사 질문이 나왔을 때 "이 유형이면 A/B/C 중 어느 정도 개입이 필요했는지" 바로 참고할 수 있도록 구조화했습니다.

## 🧩 Semantic Layer 파일럿 실험 (toxicology DB)

옵션 1(query rewriting)·옵션 2(ambiguity detection)가 모호성을 **사후에** 처리하는 반응형 접근이라면, semantic layer는 마크다운 런북으로 도메인 지식·비즈니스 정의를 미리 제공해 구조적 모호성을 **사전에** 해소하는 접근입니다. 모델 자체는 수정하지 않고, 프롬프트에 주는 컨텍스트만 바꿉니다.

### 런북 작성 방식

toxicology DB 40문항을 **build set 10개 / excluded 3개(gold·evidence 자체 오류로 판단) / held-out 27개**로 분리했습니다. 런북은 두 단계로 작성했습니다.

- **Phase A**: DDL과 BIRD 공식 database description만으로 하향식 분석 (테이블 선택, 조인 경로, 데이터 관례 등)
- **Phase B**: build set 10개의 실제 오답(predicted_sql vs gold_sql)을 역추적해 상향식으로 보강 (예: `DIVIDE()`가 실제 함수가 아니라 pseudocode라는 규칙, `atom_id1`이 아니라 `atom_id2`라는 컬럼명 규칙 등)

held-out 27개는 런북 제작에 일절 참조하지 않아, "특정 문항 암기"가 아닌 일반화 가능한 규칙인지 검증할 수 있게 설계했습니다.

### 실험 설계: 4-condition 비교

held-out 27문항에 대해, 같은 질문·같은 모델(gpt-4o-mini)·같은 조립 방식에서 **컨텍스트로 무엇을 주는지만** 바꿔 비교했습니다.

| Condition | 제공 컨텍스트 |
|---|---|
| A. raw | 스키마만 |
| B. semlayer_a | 스키마 + 런북(Phase A만, ablation) |
| C. semlayer | 스키마 + 런북(Phase A+B 결합) |
| D. evidence | 스키마 + BIRD 원본 hint (oracle 상한선) |

### 결과 (n=27)

| Condition | EX |
|---|---|
| raw | 22.2% (6/27) |
| semlayer_a (Phase A만) | 40.7% (11/27) |
| semlayer (Phase A+B) | 48.1% (13/27) |
| evidence (oracle) | 66.7% (18/27) |

**Pairwise McNemar exact test:**

| 비교 | p-value | 유의성 |
|---|---|---|
| raw vs semlayer_a | 0.0625 | n.s. |
| raw vs semlayer | 0.0654 | n.s. (경계) |
| raw vs evidence | 0.0005 | *** |
| semlayer_a vs semlayer | 0.7266 | n.s. |
| semlayer_a vs evidence | 0.0391 | * |
| semlayer vs evidence | 0.1797 | n.s. |

### 회귀 / 일반화 분석 (raw → semlayer, held-out 27개 실측 기준)

- **회귀** (raw에서 맞았는데 semlayer에서 틀림): 2건 (q213, q230)
- **일반화** (raw에서 틀렸는데 semlayer에서 새로 맞음): 9건 (q220, q226, q227, q232, q243, q253, q255, q260, q327)
- 순증감: +7문항 (6개 → 13개와 일치)

### 해석

- 런북 투입 후 정확도는 raw 대비 두 배 이상(22.2% → 48.1%) 올랐지만, n=27이라는 표본 크기 한계로 raw vs semlayer는 통계적으로 유의 수준에 근소하게 못 미칩니다(p=0.065). 표본을 늘려야 확정적 결론이 가능합니다.
- Phase B(오답 역추적 보강)가 Phase A(스키마 기반 하향식) 단독보다 조금 더 나은 정도(40.7% → 48.1%)이며 이 차이도 유의하지 않습니다(p=0.73) — 이번 build set(10개) 규모로는 Phase B의 추가 기여가 통계적으로 뚜렷하게 갈리지 않았습니다.
- evidence(oracle) 조건이 여전히 가장 높지만, semlayer와 evidence 간 차이(48.1% vs 66.7%)는 유의하지 않습니다(p=0.18) — 런북이 oracle hint와 통계적으로 구별하기 어려운 수준까지 격차를 좁혔을 가능성이 있으나, 이 역시 표본 크기 때문에 단정하기는 이릅니다.
- 회귀(2건) < 일반화(9건)로, 런북이 새로 해결한 문항이 부작용으로 틀리게 만든 문항보다 많았습니다 — self-correction 실험에서 확인했던 "overcorrection risk가 낮다"는 경향과 방향이 일치합니다.

## 🔮 Future Work

- Few-shot 예시를 통한 출력 형식 정확도 개선
- Semantic layer 파일럿을 toxicology 외 다른 DB로 확장 → build set 규모를 키워 통계적 검정력 확보
- `analyze_semantic_layer.py`의 회귀/일반화 분석 로직을 하드코딩된 추정 리스트 대신 매 실행마다의 raw 조건 실측 결과 기준으로 계산하도록 수정
- toxicology 외 다른 DB로 self-correction / clarification 실험 확장, 카테고리 taxonomy 일반화
- 벡터DB 기반 feedback 로그 검색 (현재는 JSON 저장까지만 구현, 유사 질문 retrieval은 다음 단계)
- LangGraph 기반 multi-step pipeline으로 확장

## 🛠 Tech Stack

Python · OpenAI API (gpt-4o-mini, gpt-5.5) · SQLite
