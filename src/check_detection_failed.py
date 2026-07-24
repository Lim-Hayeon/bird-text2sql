import sqlite3
conn = sqlite3.connect("../data/mini_dev_data/dev_databases/toxicology/toxicology.sqlite")
cur = conn.cursor()
try:
    cur.execute("""SELECT a1.atom_id, a2.atom_id 
FROM connected c 
JOIN bond b ON c.bond_id = b.bond_id 
JOIN atom a1 ON c.atom_id1 = a1.atom_id 
JOIN atom a2 ON c.atom_id2 = a2.atom_id 
WHERE b.molecule_id = 'TR041' AND b.bond_type = '#'""")
    print(cur.fetchall())
except Exception as e:
    print("에러:", e)