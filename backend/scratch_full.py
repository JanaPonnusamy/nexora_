import time, pyodbc, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
from config.database import _connection_string

cs = _connection_string()

def connect():
    c = pyodbc.connect(cs, timeout=15); c.timeout = 90
    return c

c = connect(); cur = c.cursor()
cur.execute("SELECT TOP 1 tenant_id FROM sync.Products WHERE ProductName LIKE 'CREVAST%'")
tid = cur.fetchone()[0]

def run(sql, params):
    """execute on warm conn, reconnect once on drop."""
    global c, cur
    for attempt in (1, 2):
        try:
            cur.execute(sql, params)
            return cur.fetchall(), cur
        except pyodbc.Error:
            c = connect(); cur = c.cursor()
    raise RuntimeError("gave up")

# 1) the search (warm)
t = time.time()
rows, cur = run("EXEC stock.usp_ProductSearch @TenantId=?,@SearchText=?,@OnlyStock=?", (tid, 'crevast', 0))
search_dt = time.time()-t
# top product per store, like the client
seen = {}
for r in rows:
    d = dict(zip([d[0] for d in cur.description], r))
    sid = str(d['store_id'])
    if sid not in seen:
        seen[sid] = int(d['product_code'])
print("search (warm): %.2fs, stores=%d" % (search_dt, len(seen)), flush=True)

# 2) the 6 ProductCore calls (warm), sequential -- multi-resultset
core_total = 0.0
for sid, pc in seen.items():
    t = time.time()
    try:
        cur.execute("EXEC stock.usp_ProductCore @TenantId=?,@StoreId=?,@ProductCode=?,@Months=?", (tid, sid, pc, 4))
        # drain all 4 result sets
        while True:
            try: cur.fetchall()
            except pyodbc.ProgrammingError: pass
            if not cur.nextset(): break
    except pyodbc.Error:
        c = connect(); cur = c.cursor()
    dt = time.time()-t; core_total += dt
    print("  core %s: %.2fs" % (sid[:8], dt), flush=True)

print("CORE total (warm, sequential): %.2fs" % core_total, flush=True)
print("=> pure server-side for whole screen ~ %.2fs (search + cores)" % (search_dt + core_total), flush=True)
c.close()
