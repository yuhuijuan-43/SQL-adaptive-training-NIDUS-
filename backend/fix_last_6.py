"""Fix remaining 6 by adding specific missing rows."""
import json, re, sqlite3

path = r'E:\SQL自适应训练\questions.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'(\[.*\])', content, re.DOTALL)
qs = json.loads(m.group(1))

def make_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    return conn

def gen(data, sql):
    conn = make_conn()
    try:
        for s in re.split(r';\s*', data.strip()):
            s = s.strip()
            if s and not s.startswith('--'): conn.execute(s)
        cur = conn.execute(sql)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        if not rows: conn.close(); return ''
        ws = [max(len(n), max((len(str(v) if v is not None else 'NULL') for v in [row[i] for row in rows]), default=0)) for i, n in enumerate(cols)]
        lines = [' | '.join(n.ljust(ws[i]) for i,n in enumerate(cols))]
        if len(cols) == 1:
            w = sum(ws) + 3 * (len(cols) - 1)
            half = w // 2
            lines.append('-' * half + '-+-' + '-' * (w - half - 3))
        else:
            lines.append('-+-'.join('-'*w for w in ws))
        for row in rows:
            vals = [str(row[i]) if row[i] is not None else 'NULL' for i in range(len(cols))]
            lines.append(' | '.join(v.ljust(ws[i]) for i,v in enumerate(vals)))
        conn.close(); return '\n'.join(lines)
    except: conn.close(); return ''

fixes = {
    'Bender': {
        'extra': "INSERT INTO goal VALUES (1002,'ENG','Bender',85);",
        'schema': 'CREATE TABLE game (id INT, mdate TEXT, stadium TEXT, team1 TEXT, team2 TEXT);CREATE TABLE goal (matchid INT, teamid TEXT, player TEXT, gtime INT);',
        'data': "INSERT INTO game VALUES (1002,'2017-06-05','Wembley','ENG','ITA');INSERT INTO goal VALUES (1002,'ENG','Harry Kane',15);INSERT INTO goal VALUES (1002,'ITA','Andrea Belotti',30);INSERT INTO goal VALUES (1002,'ENG','Bender',85);",
    },
    'Star Trek': {
        'extra': "INSERT INTO movie VALUES (10,'Star Trek: The Motion Picture',1979,46000000);",
        'schema': 'CREATE TABLE movie (id INT, title TEXT, yr INT, budget BIGINT);',
        'data': "INSERT INTO movie VALUES (1,'Citizen Kane',1941,700000);INSERT INTO movie VALUES (2,'Star Trek: The Motion Picture',1979,46000000);",
    },
    'Rock Hudson': {
        'extra': "INSERT INTO movie VALUES (10,'Movie1',1960,1000000);INSERT INTO movie VALUES (11,'Movie2',1961,1000000);INSERT INTO movie VALUES (12,'Movie3',1962,1000000);INSERT INTO movie VALUES (13,'Movie4',1963,1000000);INSERT INTO movie VALUES (14,'Movie5',1964,1000000);INSERT INTO movie VALUES (15,'Movie6',1965,1000000);INSERT INTO movie VALUES (16,'Movie7',1966,1000000);INSERT INTO movie VALUES (17,'Movie8',1967,1000000);INSERT INTO movie VALUES (18,'Movie9',1968,1000000);INSERT INTO movie VALUES (19,'Movie10',1969,1000000);INSERT INTO movie VALUES (20,'Movie11',1970,1000000);INSERT INTO movie VALUES (21,'Movie12',1971,1000000);INSERT INTO movie VALUES (22,'Movie13',1972,1000000);INSERT INTO movie VALUES (23,'Movie14',1973,1000000);INSERT INTO movie VALUES (24,'Movie15',1974,1000000);INSERT INTO casting VALUES (10,4,1);INSERT INTO casting VALUES (11,4,1);INSERT INTO casting VALUES (12,4,1);INSERT INTO casting VALUES (13,4,1);INSERT INTO casting VALUES (14,4,1);INSERT INTO casting VALUES (15,4,1);INSERT INTO casting VALUES (16,4,1);INSERT INTO casting VALUES (17,4,1);INSERT INTO casting VALUES (18,4,1);INSERT INTO casting VALUES (19,4,1);INSERT INTO casting VALUES (20,4,1);INSERT INTO casting VALUES (21,4,1);INSERT INTO casting VALUES (22,4,1);INSERT INTO casting VALUES (23,4,1);INSERT INTO casting VALUES (24,4,1);",
        'schema': 'CREATE TABLE movie (id INT, title TEXT, yr INT, budget BIGINT);CREATE TABLE actor (id INT, name TEXT);CREATE TABLE casting (movieid INT, actorid INT, ord INT);',
        'data': "INSERT INTO actor VALUES (4,'Rock Hudson');INSERT INTO movie VALUES (6,'Pillow Talk',1959,3000000);INSERT INTO casting VALUES (6,4,1);" + "INSERT INTO movie VALUES (10,'Movie1',1960,1000000);INSERT INTO casting VALUES (10,4,1);INSERT INTO movie VALUES (11,'Movie2',1961,1000000);INSERT INTO casting VALUES (11,4,1);INSERT INTO movie VALUES (12,'Movie3',1962,1000000);INSERT INTO casting VALUES (12,4,1);INSERT INTO movie VALUES (13,'Movie4',1963,1000000);INSERT INTO casting VALUES (13,4,1);INSERT INTO movie VALUES (14,'Movie5',1964,1000000);INSERT INTO casting VALUES (14,4,1);INSERT INTO movie VALUES (15,'Movie6',1965,1000000);INSERT INTO casting VALUES (15,4,1);INSERT INTO movie VALUES (16,'Movie7',1966,1000000);INSERT INTO casting VALUES (16,4,1);INSERT INTO movie VALUES (17,'Movie8',1967,1000000);INSERT INTO casting VALUES (17,4,1);INSERT INTO movie VALUES (18,'Movie9',1968,1000000);INSERT INTO casting VALUES (18,4,1);INSERT INTO movie VALUES (19,'Movie10',1969,1000000);INSERT INTO casting VALUES (19,4,1);INSERT INTO movie VALUES (20,'Movie11',1970,1000000);INSERT INTO casting VALUES (20,4,1);INSERT INTO movie VALUES (21,'Movie12',1971,1000000);INSERT INTO casting VALUES (21,4,1);INSERT INTO movie VALUES (22,'Movie13',1972,1000000);INSERT INTO casting VALUES (22,4,1);INSERT INTO movie VALUES (23,'Movie14',1973,1000000);INSERT INTO casting VALUES (23,4,1);INSERT INTO movie VALUES (24,'Movie15',1974,1000000);INSERT INTO casting VALUES (24,4,1);",
    },
    'route_4': {
        'extra': "INSERT INTO route VALUES ('4','LRT',1,1);",
        'schema': 'CREATE TABLE stops (id INT, name TEXT);CREATE TABLE route (num TEXT, company TEXT, pos INT, stop INT);',
        'data': "INSERT INTO stops VALUES (1,'Craiglockhart');INSERT INTO route VALUES ('4','LRT',1,1);",
    },
    'stop_149_53': {
        'extra': "INSERT INTO route VALUES ('4','LRT',1,53);INSERT INTO route VALUES ('4','LRT',2,149);",
        'schema': 'CREATE TABLE route (num TEXT, company TEXT, pos INT, stop INT);',
        'data': "INSERT INTO route VALUES ('4','LRT',1,53);INSERT INTO route VALUES ('4','LRT',2,149);",
    },
}

fixed = 0
for q in qs:
    if q.get('expected_output') and q['expected_output'] != '(空结果)':
        continue
    sql = q.get('correct_answer', '')
    title = q.get('title', '')
    
    key = None
    if 'Bender' in sql: key = 'Bender'
    elif 'Star Trek' in sql: key = 'Star Trek'
    elif 'Rock Hudson' in sql or ('COUNT(movieid)>=15' in sql): key = 'Rock Hudson'
    elif 'num=' in sql and '4' in sql: key = 'route_4'
    elif 'stop=149' in sql or 'stop=53' in sql: key = 'stop_149_53'
    
    if key and key in fixes:
        f = fixes[key]
        q['table_schema'] = f['schema']
        q['initial_data'] = f['data']
        out = gen(f['data'], sql)
        if out:
            q['expected_output'] = out
            fixed += 1
            print(f'Fixed: {title[:50]}')

print(f'\nFixed: {fixed}')
missing = [q for q in qs if not q.get('expected_output') or q['expected_output'] == '(空结果)']
print(f'Remaining: {len(missing)}')
for q in missing:
    print(f'  {q["title"][:50]}')

with open(path, 'w', encoding='utf-8') as f:
    f.write('[\n')
    for i, q in enumerate(qs):
        f.write(json.dumps(q, ensure_ascii=False, indent=4))
        if i < len(qs)-1: f.write(',\n')
        else: f.write('\n')
    f.write(']\n')
print('Done.')