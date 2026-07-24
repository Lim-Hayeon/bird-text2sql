import json
import sqlite3
import time
import math
from pathlib import Path

DB_ROOT = Path('../data/mini_dev_data/dev_databases')


def execute_sql(db_path, sql, timeout=15.0):
    try:
        conn = sqlite3.connect(db_path)
        start = time.time()
        def handler():
            return 1 if time.time() - start > timeout else 0
        conn.set_progress_handler(handler, 1000)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return None


def close_enough(pred, gold, rel_tol=1e-6, abs_tol=1e-9):
    if pred is None or gold is None:
        return False
    if len(pred) != len(gold):
        return False
    try:
        pred_sorted = sorted(pred)
        gold_sorted = sorted(gold)
    except TypeError:
        pred_sorted = sorted(pred, key=str)
        gold_sorted = sorted(gold, key=str)

    for p_row, g_row in zip(pred_sorted, gold_sorted):
        if len(p_row) != len(g_row):
            return False
        for p_val, g_val in zip(p_row, g_row):
            if isinstance(p_val, (int, float)) and isinstance(g_val, (int, float)):
                if not math.isclose(p_val, g_val, rel_tol=rel_tol, abs_tol=abs_tol):
                    return False
            else:
                if p_val != g_val:
                    return False
    return True


with open('../results/error_analysis/wrong_cases.json') as f:
    wrong = json.load(f)

pseudo_funcs = ['DIVIDE(', 'SUBTRACT(', 'MULTIPLY(', 'YEAR(', 'DATE_FORMAT(', 'FROM dual', 'FROM DUAL']
near_miss = []

for w in wrong:
    if any(fn in w['predicted_sql'] for fn in pseudo_funcs):
        continue
    db_path = DB_ROOT / w['db_id'] / f"{w['db_id']}.sqlite"
    pred = execute_sql(str(db_path), w['predicted_sql'])
    gold = execute_sql(str(db_path), w['gold_sql'])
    if pred is None or gold is None:
        continue
    if set(pred) == set(gold):
        continue  # 이미 정답 처리됐어야 하는데 여기 있으면 이상한 것 (스킵)
    if close_enough(pred, gold):
        near_miss.append({
            'question_id': w['question_id'],
            'db_id': w['db_id'],
            'question': w['question'],
            'pred_result': pred,
            'gold_result': gold,
        })

print(f'전체 오답 293개 중, 부동소수점 오차로 인한 near-miss: {len(near_miss)}개\n')
for n in near_miss:
    print(f"- [{n['db_id']}] {n['question'][:60]}")
    print(f"    GOLD: {n['gold_result']}")
    print(f"    PRED: {n['pred_result']}")
