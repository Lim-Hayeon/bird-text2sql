# BIRD Text-to-SQL Pipeline

NLQ + Schema + Hint -> LLM -> SQL 파이프라인.
BIRD dev set 기준 EX(%) 측정 및 오류 케이스 10개 분석.

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 이후 .env 안에 실제 API key 채워넣기
```

## Structure
- `src/pipeline.py` — NLQ + schema + hint -> LLM -> SQL
- `src/prompts.py` — prompt template
- `src/evaluate.py` — EX(%) 계산
- `results/` — 예측 결과 및 오류 분석
