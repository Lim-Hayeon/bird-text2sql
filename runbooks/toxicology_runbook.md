

Toxicology runbook · MD
Toxicology DB — Semantic Layer Runbook
이 문서는 BIRD Mini-Dev의 toxicology DB를 대상으로 한 semantic layer 런북입니다. 모델(스키마 생성 프롬프트)에 스키마와 함께 제공되어, 도메인 지식·비즈니스 정의를 사전에 명시함으로써 구조적 모호성을 사전 해소하는 것을 목표로 합니다.

작성 방식: Phase A(스키마·공식 문서 기반 하향식 분석) → Phase B(실제 오답 역추적 기반 상향식 보강)의 2단계로 작성되었습니다. 각 항목에는 출처를 표기했습니다.

[Phase A]: DDL과 BIRD 공식 database_description만으로 도출된 규칙
[Phase B]: 모델의 실제 오답(predicted_sql vs gold_sql)을 역추적해 도출된 규칙
Build / Held-out 분리: toxicology DB 40문항 중 Phase B 규칙 근거로 사용된 문항은 build set 10개(q197, q198, q200, q218, q219, q231, q248, q263, q273, q281)로 한정했습니다. 나머지 30개는 held-out test set으로 런북 제작에 일절 참조하지 않았으며, 이후 raw / evidence / semantic-layer 3-condition 비교 실험은 이 held-out 30개로만 진행합니다 (Tk-Boost 논문의 25:75 train/test 분리 관례를 참고함). 이는 런북이 특정 문항의 정답을 "암기"한 것이 아니라 일반화 가능한 규칙인지 검증하기 위함입니다.

0. Evidence 필드 해석 규칙 [Phase B 신규]
BIRD evidence에 등장하는 DIVIDE(a, b), SUBTRACT(a, b)는 실제 SQL 함수가 아니라 "a를 b로 나눈다/뺀다"는 의미의 pseudocode다. SQLite에는 해당 함수가 존재하지 않으므로 반드시 산술 연산(a * 1.0 / b, CAST(a AS REAL) / b)으로 변환해서 작성해야 한다. 정수 나눗셈으로 인한 0 반환을 피하기 위해 분자 또는 분모 중 하나를 REAL로 캐스팅한다. — 출처(build set): q198, q219, q263 (3건). 참고: 동일 패턴이 전체 BIRD Mini-Dev 500문항 오답 293건 중 30건(10.2%)에서도 반복 확인됨 (별도 실행 통계, held-out 문항과 무관한 벤치마크 전체 집계).
1. Table 선택 규칙 [Phase A]
molecule: 분자 단위 정보 (식별자, 발암성 여부)
atom: 분자에 속한 개별 원자 정보
bond: 분자 내 두 원자 사이의 결합 정보
connected: 하나의 bond가 정확히 어느 두 atom을 잇는지 나타내는 관계 테이블
2. Measure 및 계산식 정의
[Phase A] 발암성(carcinogenic) = molecule.label = '+'
[Phase A] 비발암성(non-carcinogenic) = molecule.label = '-'
[Phase A] 단일/이중/삼중 결합 = bond.bond_type의 '-' / '=' / '#'
[Phase B 추가] "평균/비율/퍼센트"를 계산할 때, atom → connected → bond 경로로 조인하면 원자 하나가 여러 row로 중복될 수 있다(한 원자가 여러 결합에 참여하므로). 분모가 "distinct 분자 수"인지 "distinct 원자 수"인지 "row 개수"인지 질문을 정확히 읽고, 필요시 서브쿼리로 먼저 집계 단위를 GROUP BY 한 뒤 바깥에서 다시 AVG/비율 계산을 해야 한다. — 출처(build set): q198, q219, q263 (3건)
3. 조인 경로
[Phase A] atom.molecule_id = molecule.molecule_id
[Phase A] bond.molecule_id = molecule.molecule_id
[Phase A] connected.atom_id = atom.atom_id / connected.atom_id2 = atom.atom_id
[Phase A] connected.bond_id = bond.bond_id
[Phase B 확정] atom과 bond를 "같은 분자에 속하는지" 기준으로만 연결할 때는 molecule_id로 직접 조인하면 되고, connected 테이블을 거칠 필요가 없다. connected는 "이 결합이 정확히 어느 두 원자 사이인지"를 물을 때만 필요하다. — 출처(build set): q197 (불필요한 connected 경유로 결과 왜곡)
4. 데이터 관례 및 특이사항
[Phase A] atom_id 형식: {molecule_id}_{순번} (예: TR000_1)
[Phase A] bond_id 형식: {molecule_id}_{원자순번1}_{원자순번2} (예: TR004_8_9)
[Phase A] element 값은 소문자 원소 기호: cl(염소), c(탄소), h(수소), o(산소), s(황), n(질소), p(인), na(나트륨), br(브롬), f(불소), i(요오드), sn(주석), pb(납), te(텔루륨), ca(칼슘)
[Phase B 추가] connected 테이블에서 한 결합의 두 원자는 atom_id, atom_id2 두 컬럼으로 표현된다. atom_id1이라는 컬럼은 존재하지 않는다. — 출처(build set): q248 (모델이 존재하지 않는 atom_id1을 추측 → 실행 에러)
[Phase B 추가] atom_id에서 순번을 파싱할 때는 문자열 뒤에서부터 잘라야 하며(SUBSTR(atom_id, -1)), 두 자리 순번(10번대 이상)이 섞여 있을 수 있으므로 LENGTH(atom_id) = 7 같은 길이 조건으로 한 자리/두 자리를 구분해야 한다. 앞에서부터 고정 위치로 파싱하면 안 된다. — 출처(build set): q281 (앞에서부터 고정 위치 파싱 시도 → 두 자리 순번에서 오류)
[Phase B 추가] molecule_id는 atom, molecule, bond 테이블에 공통으로 존재한다. 두 테이블 이상을 조인할 때 molecule_id를 조건절이나 SELECT에 쓸 경우 반드시 테이블 alias로 명시해야 한다 (ambiguous column name 에러 방지). — 출처(build set): q273
5. 모호성 해소 규칙 [Phase A에서는 공란 → Phase B가 채움]
[Phase B] "X 원소를 포함하지 않는다"는 그 분자를 이루는 모든 원자를 확인했을 때 X가 하나도 없다는 뜻이다. "X가 아닌 원자가 하나라도 있다"는 의미가 아니다. — 출처(build set): q218
6. 출력 형식 관례 [Phase B 신규]
"Find/What/Which X" 형태의 질문은, 명시적 언급이 없는 한 식별자(ID)만 반환한다. 판단에 사용된 조건 컬럼(예: label)이나 집계값(예: COUNT)은 이미 WHERE/HAVING에서 걸러졌다면 SELECT에 다시 포함하지 않는다. — 출처(build set): q200, q231 (2건). 참고: 동일 패턴이 전체 BIRD Mini-Dev 500문항 오답 293건 중 117건(39.9%)으로 최대 오류 원인 (별도 실행 통계, held-out 문항과 무관한 벤치마크 전체 집계).
Appendix. 문서 검증 노트
BIRD 공식 database_description(molecule.csv)에서 "+"/"-" 값 설명이 molecule_id 행에 잘못 배치되어 있음을 확인함 (실제로는 label 컬럼 설명). 본 런북 작성 시 정정해서 반영함 (섹션 2 참고).
q234, q244, q247 3건은 BIRD gold SQL 또는 evidence 자체의 오류로 판단되어 런북 규칙에서 제외함 (build/held-out 어느 쪽에도 규칙 근거로 쓰지 않음). q273은 evidence 값 자체는 오류이나('pb' vs 질문의 chlorine), 발생한 에러(ambiguous column name)는 재현 가능한 일반 패턴이라 판단해 섹션 4에 규칙으로 반영함.
Appendix. 규칙-오답 매핑표 (build set 기준)
규칙 ID	섹션	출처	근거 문항(build)	요약
R0	0. Evidence 해석	Phase B	q198, q219, q263 (3건)	DIVIDE는 함수 아님 → 산술 연산 변환
R1	3. 조인 경로	Phase B	q197	atom-bond 직접 조인, connected 불필요
R2	2. Measure	Phase B	q198, q219, q263 (3건)	비율 계산 시 집계 단위 명확화
R3	4. 데이터 관례	Phase B	q248	atom_id2 컬럼명 (atom_id1 없음)
R4	4. 데이터 관례	Phase B	q281	atom_id 순번 파싱, 뒤에서부터
R5	4. 데이터 관례	Phase B	q273	molecule_id 중복 컬럼, alias 필수
R6	5. 모호성	Phase B	q218	"포함 안 함" = 전체 원자 기준
R7	6. 출력 형식	Phase B	q200, q231 (2건)	식별자만 반환, 부가 컬럼 제외
Appendix. Build / Held-out 문항 분리 (실험용)
toxicology DB 40문항 = build 10 + excluded 3 + held-out 27

Build set (10개, 런북 제작에 사용, 3-condition 평가에서 제외) q197, q198, q200, q218, q219, q231, q248, q263, q273, q281

Excluded (3개, gold/evidence 자체 오류로 판단, 어느 쪽 평가에도 미포함) q234, q244, q247

Held-out test set (27개, raw / evidence / semantic-layer 3-condition 비교는 이 문항만으로 진행) q195, q201, q206, q207, q208, q212, q213, q215, q220, q226, q227, q228, q230, q232, q236, q239, q240, q242, q243, q245, q249, q253, q255, q260, q268, q282, q327

Held-out 27개 중 stable_correct(원래 raw 조건에서도 정답)였던 문항이 다수 포함되어 있으므로, 3-condition 비교 시 (1) 원래 정답이던 문항을 semantic layer가 오히려 틀리게 만들지 않는지(회귀 여부)와 (2) 원래 오답이던 문항 (q207, q215, q239, q227, q228, q282 등)을 semantic layer가 새롭게 맞히는지 (일반화 여부) 두 가지를 함께 확인한다.


