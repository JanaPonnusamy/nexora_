"""Verify SQLAlchemy raw QueuePool semantics WITHOUT touching .73:
   - .close() returns the connection to the pool (reuse, not physical close)
   - pre_ping detects a dead connection and transparently makes a new one
   - cursor()/commit()/rollback() delegate to the underlying DBAPI conn
"""
from sqlalchemy.pool import QueuePool
from sqlalchemy import event, exc

made = {"n": 0}
class FakeCursor:
    def execute(self, *a, **k): return self
    def fetchone(self): return (1,)
    def close(self): pass
class FakeConn:
    def __init__(self):
        made["n"] += 1
        self.id = made["n"]
        self.alive = True
    def cursor(self):
        if not self.alive:
            raise Exception("dead connection")
        return FakeCursor()
    def rollback(self):
        if not self.alive:
            raise Exception("dead on rollback")
    def commit(self): pass
    def close(self): self.alive = False

def creator():
    return FakeConn()

pool = QueuePool(creator, pool_size=2, max_overflow=2, timeout=5, recycle=1800)

@event.listens_for(pool, "checkout")
def _ping(dbapi_conn, conn_record, conn_proxy):
    try:
        cur = dbapi_conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
    except Exception:
        raise exc.DisconnectionError()  # pool discards & retries with a fresh conn

c1 = pool.connect(); id1 = c1.driver_connection.id
print("checkout #1 -> conn", id1, "| made so far:", made["n"])
c1.close()  # return to pool
c2 = pool.connect(); id2 = c2.driver_connection.id
print("checkout #2 -> conn", id2, "| reused?", id1 == id2, "| made so far:", made["n"])

# kill the underlying connection while checked-in, then check out again:
# pre_ping should detect the dead conn and create a fresh one.
c2.driver_connection.close()   # mark underlying dead
c2.close()                     # return the (now dead) conn to pool
c3 = pool.connect(); id3 = c3.driver_connection.id
print("checkout #3 after kill -> conn", id3, "| new one made?", id3 != id2, "| made so far:", made["n"])
cur = c3.cursor(); print("cursor works after reconnect:", cur.execute("SELECT 1").fetchone())
c3.close()
print("OK")
