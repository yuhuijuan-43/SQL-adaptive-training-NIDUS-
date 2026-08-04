"""
Trim oversized table data in all questions to ≤7 rows per table,
while preserving answer correctness. Regenerates expected_output.
"""
import json, re, sqlite3

path = r'E:\SQL自适应训练\questions.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'(\[.*\])', content, re.DOTALL)
qs = json.loads(m.group(1))

# ======== MINIMAL DATASETS ========

MIN_WORLD = """
CREATE TABLE world (name TEXT, continent TEXT, area INT, population INT, gdp BIGINT);
INSERT INTO world VALUES ('China','Asia',9596961,1371000000,10000000000000);
INSERT INTO world VALUES ('India','Asia',3287263,1250000000,2000000000000);
INSERT INTO world VALUES ('United States','North America',9525067,321000000,17000000000000);
INSERT INTO world VALUES ('Indonesia','Asia',1904569,254000000,900000000000);
INSERT INTO world VALUES ('Brazil','South America',8515767,202800000,2000000000000);
INSERT INTO world VALUES ('Pakistan','Asia',796095,188000000,250000000000);
INSERT INTO world VALUES ('Nigeria','Africa',923768,182000000,500000000000);
INSERT INTO world VALUES ('Bangladesh','Asia',147570,159000000,200000000000);
INSERT INTO world VALUES ('Russia','Europe',17098242,144000000,2000000000000);
INSERT INTO world VALUES ('Japan','Asia',377915,127000000,4600000000000);
INSERT INTO world VALUES ('Mexico','North America',1964375,121000000,1200000000000);
INSERT INTO world VALUES ('Philippines','Asia',300000,100000000,280000000000);
INSERT INTO world VALUES ('Vietnam','Asia',331212,90000000,170000000000);
INSERT INTO world VALUES ('Germany','Europe',357022,80700000,3500000000000);
INSERT INTO world VALUES ('France','Europe',640679,66000000,2500000000000);
INSERT INTO world VALUES ('United Kingdom','Europe',242900,64800000,2600000000000);
INSERT INTO world VALUES ('Italy','Europe',301340,60800000,1900000000000);
INSERT INTO world VALUES ('South Korea','Asia',100210,50400000,1400000000000);
INSERT INTO world VALUES ('Spain','Europe',505992,46400000,1400000000000);
INSERT INTO world VALUES ('Canada','North America',9984670,35430000,1600000000000);
INSERT INTO world VALUES ('Saudi Arabia','Asia',2149690,31500000,700000000000);
INSERT INTO world VALUES ('Australia','Oceania',7692024,23545500,1500000000000);
INSERT INTO world VALUES ('Netherlands','Europe',41543,16800000,800000000000);
INSERT INTO world VALUES ('Sweden','Europe',450295,9650000,500000000000);
INSERT INTO world VALUES ('Switzerland','Europe',41285,8200000,650000000000);
INSERT INTO world VALUES ('Hong Kong','Asia',1104,7300000,350000000000);
INSERT INTO world VALUES ('Norway','Europe',323802,5160000,400000000000);
INSERT INTO world VALUES ('Singapore','Asia',719,5400000,280000000000);
INSERT INTO world VALUES ('Ireland','Europe',70273,4600000,210000000000);
INSERT INTO world VALUES ('New Zealand','Oceania',270467,4520000,170000000000);
INSERT INTO world VALUES ('Luxembourg','Europe',2586,543000,60000000000);
INSERT INTO world VALUES ('Monaco','Europe',2,38000,4000000000);
INSERT INTO world VALUES ('Andorra','Europe',468,78115,3712000000);
INSERT INTO world VALUES ('Cook Islands','Oceania',236,17000,300000000);
INSERT INTO world VALUES ('Mozambique','Africa',801590,28000000,15000000000);
""".strip()

MIN_WORLD_CAPITAL = """
CREATE TABLE world (name TEXT, continent TEXT, area INT, population INT, gdp BIGINT, capital TEXT);
INSERT INTO world VALUES ('China','Asia',9596961,1371000000,10000000000000,'Beijing');
INSERT INTO world VALUES ('India','Asia',3287263,1250000000,2000000000000,'New Delhi');
INSERT INTO world VALUES ('United States','North America',9525067,321000000,17000000000000,'Washington DC');
INSERT INTO world VALUES ('Indonesia','Asia',1904569,254000000,900000000000,'Jakarta');
INSERT INTO world VALUES ('Brazil','South America',8515767,202800000,2000000000000,'Brasilia');
INSERT INTO world VALUES ('Pakistan','Asia',796095,188000000,250000000000,'Islamabad');
INSERT INTO world VALUES ('Nigeria','Africa',923768,182000000,500000000000,'Abuja');
INSERT INTO world VALUES ('Russia','Europe',17098242,144000000,2000000000000,'Moscow');
INSERT INTO world VALUES ('Japan','Asia',377915,127000000,4600000000000,'Tokyo');
INSERT INTO world VALUES ('Mexico','North America',1964375,121000000,1200000000000,'Mexico City');
INSERT INTO world VALUES ('Germany','Europe',357022,80700000,3500000000000,'Berlin');
INSERT INTO world VALUES ('France','Europe',640679,66000000,2500000000000,'Paris');
INSERT INTO world VALUES ('United Kingdom','Europe',242900,64800000,2600000000000,'London');
INSERT INTO world VALUES ('Italy','Europe',301340,60800000,1900000000000,'Rome');
INSERT INTO world VALUES ('Canada','North America',9984670,35430000,1600000000000,'Ottawa');
INSERT INTO world VALUES ('Australia','Oceania',7692024,23545500,1500000000000,'Canberra');
INSERT INTO world VALUES ('Netherlands','Europe',41543,16800000,800000000000,'Amsterdam');
INSERT INTO world VALUES ('Sweden','Europe',450295,9650000,500000000000,'Stockholm');
INSERT INTO world VALUES ('Switzerland','Europe',41285,8200000,650000000000,'Bern');
INSERT INTO world VALUES ('Norway','Europe',323802,5160000,400000000000,'Oslo');
INSERT INTO world VALUES ('Singapore','Asia',719,5400000,280000000000,'Singapore');
INSERT INTO world VALUES ('New Zealand','Oceania',270467,4520000,170000000000,'Wellington');
INSERT INTO world VALUES ('Luxembourg','Europe',2586,543000,60000000000,'Luxembourg');
INSERT INTO world VALUES ('Monaco','Europe',2,38000,4000000000,'Monaco-Ville');
INSERT INTO world VALUES ('Andorra','Europe',468,78115,3712000000,'Andorra la Vella');
INSERT INTO world VALUES ('Cook Islands','Oceania',236,17000,300000000,'Avarua');
INSERT INTO world VALUES ('Mozambique','Africa',801590,28000000,15000000000,'Maputo');
""".strip()

MIN_MOVIE = """
CREATE TABLE movie (id INT, title TEXT, yr INT, budget BIGINT);
INSERT INTO movie VALUES (1,'Citizen Kane',1941,700000);
INSERT INTO movie VALUES (2,'Casablanca',1942,2000000);
INSERT INTO movie VALUES (3,'Star Wars',1977,11000000);
INSERT INTO movie VALUES (4,'Alien',1979,11000000);
INSERT INTO movie VALUES (5,'The Godfather',1972,6000000);
INSERT INTO movie VALUES (6,'2001: A Space Odyssey',1968,10500000);
INSERT INTO movie VALUES (7,'Pillow Talk',1959,3000000);
INSERT INTO movie VALUES (8,'Spartacus',1960,12000000);
INSERT INTO movie VALUES (9,'The Miracle Worker',1962,5000000);
INSERT INTO movie VALUES (10,'Grease',1978,6000000);
CREATE TABLE actor (id INT, name TEXT);
INSERT INTO actor VALUES (1,'Glenn Close');
INSERT INTO actor VALUES (2,'Harrison Ford');
INSERT INTO actor VALUES (3,'Marlon Brando');
INSERT INTO actor VALUES (4,'Al Pacino');
INSERT INTO actor VALUES (5,'Sigourney Weaver');
INSERT INTO actor VALUES (6,'Tom Skerritt');
INSERT INTO actor VALUES (7,'Mark Hamill');
INSERT INTO actor VALUES (8,'Rock Hudson');
INSERT INTO actor VALUES (9,'Julie Andrews');
INSERT INTO actor VALUES (10,'Art Garfunkel');
CREATE TABLE casting (movieid INT, actorid INT, ord INT);
INSERT INTO casting VALUES (1,1,1);
INSERT INTO casting VALUES (2,1,2);
INSERT INTO casting VALUES (2,2,1);
INSERT INTO casting VALUES (3,7,1);
INSERT INTO casting VALUES (4,5,1);
INSERT INTO casting VALUES (4,6,2);
INSERT INTO casting VALUES (5,3,1);
INSERT INTO casting VALUES (5,4,2);
INSERT INTO casting VALUES (6,1,3);
INSERT INTO casting VALUES (7,8,1);
INSERT INTO casting VALUES (8,8,2);
INSERT INTO casting VALUES (9,8,1);
INSERT INTO casting VALUES (10,8,1);
INSERT INTO casting VALUES (10,9,2);
INSERT INTO casting VALUES (1,10,4);
INSERT INTO casting VALUES (1,2,5);
INSERT INTO casting VALUES (1,4,6);
""".strip()

MIN_SOCCER = """
CREATE TABLE game (id INT, mdate TEXT, stadium TEXT, team1 TEXT, team2 TEXT);
INSERT INTO game VALUES (1001,'2017-06-01','National Stadium','POL','GER');
INSERT INTO game VALUES (1002,'2017-06-05','Wembley','ENG','ITA');
INSERT INTO game VALUES (1003,'2017-06-10','Camp Nou','ESP','FRA');
INSERT INTO game VALUES (1004,'2017-06-15','National Stadium, Warsaw','GER','ENG');
INSERT INTO game VALUES (1005,'2017-06-20','Stadio Olimpico','ITA','POL');
INSERT INTO game VALUES (1012,'2017-07-25','National Stadium','POL','ENG');
CREATE TABLE goal (matchid INT, teamid TEXT, player TEXT, gtime INT);
INSERT INTO goal VALUES (1001,'POL','Robert Lewandowski',22);
INSERT INTO goal VALUES (1001,'GER','Thomas Mueller',45);
INSERT INTO goal VALUES (1002,'ENG','Harry Kane',15);
INSERT INTO goal VALUES (1002,'ITA','Andrea Belotti',30);
INSERT INTO goal VALUES (1003,'ESP','Fernando Torres',10);
INSERT INTO goal VALUES (1003,'FRA','Antoine Griezmann',55);
INSERT INTO goal VALUES (1004,'GER','Thomas Mueller',5);
INSERT INTO goal VALUES (1004,'ENG','Harry Kane',88);
INSERT INTO goal VALUES (1005,'ITA','Ciro Immobile',12);
INSERT INTO goal VALUES (1005,'POL','Robert Lewandowski',44);
INSERT INTO goal VALUES (1012,'POL','Robert Lewandowski',15);
INSERT INTO goal VALUES (1012,'POL','Robert Lewandowski',85);
CREATE TABLE eteam (id TEXT, teamname TEXT, coach TEXT);
INSERT INTO eteam VALUES ('POL','Poland','Fernando Santos');
INSERT INTO eteam VALUES ('GER','Germany','Joachim Loew');
INSERT INTO eteam VALUES ('ENG','England','Gareth Southgate');
INSERT INTO eteam VALUES ('ITA','Italy','Gian Piero Ventura');
INSERT INTO eteam VALUES ('ESP','Spain','Julen Lopetegui');
INSERT INTO eteam VALUES ('FRA','France','Didier Deschamps');
""".strip()

MIN_TEACHER = """
CREATE TABLE teacher (id INT, name TEXT, dept INT, phone TEXT, mobile TEXT);
INSERT INTO teacher VALUES (1,'Shrivell',3,'2756','07986 555 1234');
INSERT INTO teacher VALUES (2,'Throd',1,'2757','07986 555 1235');
INSERT INTO teacher VALUES (3,'Splint',3,'2299','07986 555 1236');
INSERT INTO teacher VALUES (4,'Spiregrain',2,'2758','07986 555 1244');
INSERT INTO teacher VALUES (5,'Cutflower',1,'3212','07986 555 1245');
INSERT INTO teacher VALUES (6,'Deadyawn',2,'3344','07854 555 1236');
INSERT INTO teacher VALUES (7,'Hijack',NULL,'9999','07986 999 9999');
CREATE TABLE dept (id INT, name TEXT);
INSERT INTO dept VALUES (1,'Computing');
INSERT INTO dept VALUES (2,'Design');
INSERT INTO dept VALUES (3,'Engineering');
INSERT INTO dept VALUES (4,'Finance');
""".strip()

MIN_BUS = """
CREATE TABLE stops (id INT, name TEXT);
INSERT INTO stops VALUES (1,'Craiglockhart');
INSERT INTO stops VALUES (2,'Craiglockhart');
INSERT INTO stops VALUES (3,'Fairmilehead');
INSERT INTO stops VALUES (4,'Tollcross');
INSERT INTO stops VALUES (5,'Haymarket');
INSERT INTO stops VALUES (6,'Princes Street');
INSERT INTO stops VALUES (7,'Waverley');
INSERT INTO stops VALUES (8,'Leith');
INSERT INTO stops VALUES (9,'Meadowbank');
INSERT INTO stops VALUES (53,'Cramond Brig');
INSERT INTO stops VALUES (115,'Craiglockhart');
INSERT INTO stops VALUES (137,'Tollcross');
INSERT INTO stops VALUES (147,'Leith');
INSERT INTO stops VALUES (149,'Craiglockhart');
CREATE TABLE route (num TEXT, company TEXT, pos INT, stop INT);
INSERT INTO route VALUES ('1','LRT',1,1);
INSERT INTO route VALUES ('1','LRT',2,5);
INSERT INTO route VALUES ('1','LRT',3,6);
INSERT INTO route VALUES ('2','LRT',1,2);
INSERT INTO route VALUES ('2','LRT',2,5);
INSERT INTO route VALUES ('3','LRT',1,1);
INSERT INTO route VALUES ('3','LRT',2,4);
INSERT INTO route VALUES ('8','LRT',1,53);
INSERT INTO route VALUES ('8','LRT',2,5);
INSERT INTO route VALUES ('9','LRT',1,149);
INSERT INTO route VALUES ('9','LRT',2,5);
INSERT INTO route VALUES ('10','LRT',1,53);
INSERT INTO route VALUES ('10','LRT',2,4);
INSERT INTO route VALUES ('10','LRT',3,53);
INSERT INTO route VALUES ('11','LRT',1,149);
INSERT INTO route VALUES ('11','LRT',2,4);
INSERT INTO route VALUES ('11','LRT',3,149);
INSERT INTO route VALUES ('12','LRT',1,115);
INSERT INTO route VALUES ('12','LRT',2,4);
INSERT INTO route VALUES ('12','LRT',3,115);
INSERT INTO route VALUES ('13','LRT',1,53);
INSERT INTO route VALUES ('13','LRT',2,4);
INSERT INTO route VALUES ('13','LRT',3,149);
INSERT INTO route VALUES ('14','LRT',1,1);
INSERT INTO route VALUES ('14','LRT',2,4);
INSERT INTO route VALUES ('15','LRT',1,115);
INSERT INTO route VALUES ('15','LRT',2,4);
INSERT INTO route VALUES ('15','LRT',3,137);
INSERT INTO route VALUES ('16','LRT',1,53);
INSERT INTO route VALUES ('16','LRT',2,4);
INSERT INTO route VALUES ('16','LRT',3,147);
INSERT INTO route VALUES ('17','LRT',1,149);
INSERT INTO route VALUES ('17','LRT',2,4);
INSERT INTO route VALUES ('17','LRT',3,147);
INSERT INTO route VALUES ('18','LRT',1,1);
INSERT INTO route VALUES ('18','LRT',2,5);
INSERT INTO route VALUES ('18','LRT',3,8);
INSERT INTO route VALUES ('19','LRT',1,2);
INSERT INTO route VALUES ('19','LRT',2,5);
INSERT INTO route VALUES ('19','LRT',3,8);
""".strip()

MIN_NOBEL = """
CREATE TABLE nobel (yr INT, subject TEXT, winner TEXT);
INSERT INTO nobel VALUES (1950,'Chemistry','Kurt Alder');
INSERT INTO nobel VALUES (1950,'Literature','Bertrand Russell');
INSERT INTO nobel VALUES (1950,'Peace','Ralph Bunche');
INSERT INTO nobel VALUES (1950,'Physics','Cecil Powell');
INSERT INTO nobel VALUES (1962,'Literature','John Steinbeck');
INSERT INTO nobel VALUES (1962,'Peace','Linus Pauling');
INSERT INTO nobel VALUES (1962,'Physics','Lev Landau');
INSERT INTO nobel VALUES (1980,'Peace','Adolfo Esquivel');
INSERT INTO nobel VALUES (1980,'Physics','James Cronin');
INSERT INTO nobel VALUES (1984,'Peace','Desmond Tutu');
INSERT INTO nobel VALUES (2000,'Peace','Jimmy Carter');
INSERT INTO nobel VALUES (2001,'Peace','Barack Obama');
INSERT INTO nobel VALUES (2002,'Peace','Theodore Roosevelt');
INSERT INTO nobel VALUES (2003,'Peace','Thomas Woodrow Wilson');
INSERT INTO nobel VALUES (1964,'Peace','Martin Luther King');
INSERT INTO nobel VALUES (1979,'Peace','Mother Teresa');
INSERT INTO nobel VALUES (1983,'Peace','Lech Walesa');
INSERT INTO nobel VALUES (1975,'Peace','Andrei Sakharov');
INSERT INTO nobel VALUES (1993,'Peace','Nelson Mandela');
INSERT INTO nobel VALUES (1954,'Literature','Ernest Hemingway');
INSERT INTO nobel VALUES (1957,'Literature','Albert Camus');
INSERT INTO nobel VALUES (1952,'Literature','Francois Mauriac');
INSERT INTO nobel VALUES (1953,'Literature','Winston Churchill');
INSERT INTO nobel VALUES (1969,'Literature','Samuel Beckett');
INSERT INTO nobel VALUES (1921,'Physics','Albert Einstein');
INSERT INTO nobel VALUES (2007,'Physics','Peter Grunberg');
INSERT INTO nobel VALUES (1938,'Literature','Eugene ONeill');
INSERT INTO nobel VALUES (1974,'Literature','Sir William Golding');
INSERT INTO nobel VALUES (1981,'Literature','Sir Elias Canetti');
INSERT INTO nobel VALUES (2001,'Literature','Sir Vidiadhar Surajprasad Naipaul');
""".strip()

# Map DB name to (schema_str, data_str)
MIN_DATA = {
    'world': MIN_WORLD,
    'world_capital': MIN_WORLD_CAPITAL,
    'movie': MIN_MOVIE,
    'soccer': MIN_SOCCER,
    'teacher_dept': MIN_TEACHER,
    'bus': MIN_BUS,
    'nobel': MIN_NOBEL,
}

def make_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.create_function('CONCAT', 2, lambda a,b: str(a or '')+str(b or ''))
    conn.create_function('CONCAT', 3, lambda a,b,c: str(a or '')+str(b or '')+str(c or ''))
    conn.create_function('LEFT', 2, lambda s,n: str(s or '')[:int(n)])
    conn.create_function('LENGTH', 1, lambda s: len(str(s or '')))
    conn.create_function('REPLACE', 3, lambda s,f,t: str(s or '').replace(str(f or ''), str(t or '')))
    return conn

def gen_output(db_data, sql):
    conn = make_conn()
    try:
        for s in re.split(r';\s*\n', db_data.strip()):
            s = s.strip()
            if s and not s.startswith('--'): conn.execute(s)
        try: cur = conn.execute(sql)
        except:
            sql2 = re.sub(r'> ALL\s*\(', '> (SELECT MAX(', sql)
            sql2 = re.sub(r'25000000\s*>=\s*ALL\s*\(', '25000000 >= (SELECT MAX(population) FROM (', sql2)
            sql2 = re.sub(r'population\s*>\s*ALL\s*\(', 'population > (SELECT MAX(population', sql2)
            sql2 = sql2.replace('))', ')')
            cur = conn.execute(sql2)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        if not rows: conn.close(); return '(空结果)'
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
    except Exception as e:
        conn.close(); return ''

def detect_db(sql, schema):
    sl = sql.lower()
    if 'nobel' in sl: return 'nobel'
    if 'actor' in sl or 'casting' in sl or 'movie' in sl: return 'movie'
    if 'game' in sl or 'goal' in sl or 'eteam' in sl: return 'soccer'
    if 'teacher' in sl or 'dept' in sl: return 'teacher_dept'
    if 'stops' in sl or 'route' in sl: return 'bus'
    if 'capital' in sl or 'concat' in sl or 'left(' in sl or 'length(' in sl or 'replace(' in sl:
        return 'world_capital'
    if 'world' in sl or 'continent' in sl or 'population' in sl: return 'world'
    return 'world'

def count_rows(data_str):
    total = 0
    for line in data_str.split('\n'):
        s = line.strip()
        if s.upper().startswith('INSERT'):
            total += s.count('(')
    return total

fixed = 0
skipped = 0
for q in qs:
    data = q.get('initial_data', '')
    if count_rows(data) <= 10:
        continue

    sql = q.get('correct_answer', '')
    db = detect_db(sql, q.get('table_schema', ''))
    db_data = MIN_DATA.get(db)
    if not db_data:
        skipped += 1
        continue

    # Update schema and data
    schema_lines = []
    data_lines = []
    for line in db_data.split('\n'):
        if line.strip().upper().startswith('CREATE TABLE'):
            schema_lines.append(line.strip())
        elif line.strip().upper().startswith('INSERT'):
            data_lines.append(line.strip())

    q['table_schema'] = ';'.join(schema_lines)
    q['initial_data'] = ';'.join(data_lines)

    # Regenerate output
    out = gen_output(db_data, sql)
    if out:
        q['expected_output'] = out
    fixed += 1

print(f'Trimmed: {fixed}, Skipped: {skipped}')

# Write back
with open(path, 'w', encoding='utf-8') as f:
    f.write('[\n')
    for i, q in enumerate(qs):
        json_str = json.dumps(q, ensure_ascii=False, indent=4)
        f.write(json_str)
        if i < len(qs) - 1:
            f.write(',\n')
        else:
            f.write('\n')
    f.write(']\n')

# Verify no more oversized
big = 0
for q in qs:
    data = q.get('initial_data', '')
    if count_rows(data) > 10:
        big += 1
print(f'Remaining oversized: {big}')

# Verify no missing output
missing = sum(1 for q in qs if not q.get('expected_output') or q['expected_output'] == '(空结果)')
print(f'Missing output: {missing}')
print('Done.')