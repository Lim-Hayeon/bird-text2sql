# Toxicology DB — Semantic Layer Runbook (Phase A Only, Ablation)

이 문서는 `toxicology_runbook.md`의 ablation 버전입니다. `[Phase A]`(DDL +
BIRD 공식 `database_description`에서 도출된 규칙)만 남기고, `[Phase B]`
(실제 오답 역추적에서 도출된 규칙)는 전부 제외했습니다.

목적: Phase B가 raw 대비 실제로 얼마나 추가적인 개선을 주는지 분리해서
측정하기 위함입니다 (Tribal Knowledge 논문의 naive knowledge vs tribal
knowledge ablation과 동일한 구조).

이 문서는 held-out 27문항 평가에서 raw / evidence / semantic-layer(A+B) 와
함께 **네 번째 조건("semlayer_a")** 으로 사용됩니다. Build/Held-out 분리는
원본 런북과 동일하게 유지됩니다 (build 10 / excluded 3 / held-out 27).

---

## 1. Table 선택 규칙

- `molecule`: 분자 단위 정보 (식별자, 발암성 여부)
- `atom`: 분자에 속한 개별 원자 정보
- `bond`: 분자 내 두 원자 사이의 결합 정보
- `connected`: 하나의 bond가 정확히 어느 두 atom을 잇는지 나타내는 관계 테이블

## 2. Measure 및 계산식 정의

- 발암성(carcinogenic) = `molecule.label = '+'`
- 비발암성(non-carcinogenic) = `molecule.label = '-'`
- 단일/이중/삼중 결합 = `bond.bond_type`의 `'-'` / `'='` / `'#'`

## 3. 조인 경로

- `atom.molecule_id = molecule.molecule_id`
- `bond.molecule_id = molecule.molecule_id`
- `connected.atom_id = atom.atom_id` / `connected.atom_id2 = atom.atom_id`
- `connected.bond_id = bond.bond_id`

## 4. 데이터 관례 및 특이사항

- `atom_id` 형식: `{molecule_id}_{순번}` (예: `TR000_1`)
- `bond_id` 형식: `{molecule_id}_{원자순번1}_{원자순번2}` (예: `TR004_8_9`)
- `element` 값은 소문자 원소 기호: cl(염소), c(탄소), h(수소), o(산소),
  s(황), n(질소), p(인), na(나트륨), br(브롬), f(불소), i(요오드),
  sn(주석), pb(납), te(텔루륨), ca(칼슘)

## 5. 모호성 해소 규칙

(Phase A 단독으로는 도출되지 않음 — 원본 런북에서도 이 섹션은 Phase B가
채운 유일한 섹션이었음)

---

참고: 원본 런북의 섹션 0(Evidence 필드 해석)과 섹션 6(출력 형식 관례)은
전적으로 Phase B에서만 발견된 패턴이라, 이 ablation 버전에는 해당
섹션 자체가 존재하지 않습니다.