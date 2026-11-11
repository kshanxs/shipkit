# Concurrency recipes

How to make requests race in an API's tests, and how to fix what they find. The examples are
FastAPI with SQLAlchemy and pytest (async); the same shapes work with any stack.

## 1. Make requests really race

A test client that shares one database session between requests makes them take turns: requests
sent together never race. Give each request its own session and connection, committed or rolled
back as production does (a `racing_client` fixture that overrides the session dependency with a
fresh session per request).

Timing alone rarely puts two requests between the same check and write. A gate does: hold each
request after its first read of a table until all `n` have read it.

```python
# tests/racing.py: the gate, built on SQLAlchemy's events
import contextlib
import threading

from sqlalchemy import event


@contextlib.contextmanager
def all_read_before_any_writes(n: int, table: str, engine, timeout: float = 5.0):
    barrier = threading.Barrier(n, timeout=timeout)
    seen: set[int] = set()

    def after(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and f" {table}" in statement and id(conn) not in seen:
            seen.add(id(conn))
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait()

    event.listen(engine.sync_engine, "after_cursor_execute", after)
    try:
        yield
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", after)
```

```python
async def test_five_creates_at_once_make_one_project(racing_client, two_tenants, engine):
    with all_read_before_any_writes(5, "projects", engine):
        answers = await asyncio.gather(*(
            racing_client.post("/api/v1/projects", headers=two_tenants.headers_a, json={"key": "WEB", "name": "Web"})
            for _ in range(5)))
    assert sorted(a.status_code for a in answers) == [201, 409, 409, 409, 409]
```

- Count the rows afterwards on a fresh session: status codes alone do not prove nothing extra was
  written.
- The data the requests read must be committed before they start; a fixture that rolls back is
  invisible to other sessions.
- `n` is the number of requests that reach the read; a request refused earlier (403) never does,
  so the gate gives up after its timeout rather than hang. With a sync driver run the requests in
  threads; with an async driver the event hook still runs per connection.

## 2. Show the test can fail

Remove the guard for one run and watch the test fail (patch the unique constraint's effect away,
or drop the lock): all five are created. Without that run, a passing race test may only show that
the requests did not overlap.

## 3. Fix it in the database

In order of preference:

1. **A unique constraint** on what must not repeat (with a migration). Two inserts cannot both
   succeed whatever the timing. Turn the loser's integrity error into a 409 with a clear message.
2. **A row lock** where the decision reads a row and changes it (a balance, a count against a
   limit, a status):

   ```python
   row = await db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
   if row.status != "open":
       raise Conflict("This invoice has already been settled")
   row.status = "paid"
   ```

   The lock lasts until the request's transaction ends. Lock rows in one order everywhere, or two
   requests wait on each other.
3. **An idempotency claim** for a client that may resend: insert a row keyed by
   (account, tenant, key) whose unique constraint stops a second run, and keep the answer.

A Python check ("does it exist?") stays useful for the clear message on the common path; it is
never the guard.

## 4. Errors halfway

The request's transaction rolls back when it raises. To show a service leaves nothing half-made,
raise partway through (patch a later step) and count rows afterwards on a fresh session.

## 5. Latency in-process

```python
import statistics, time

async def timed(client, n, at_once, call):
    gate, took = asyncio.Semaphore(at_once), []

    async def one():
        async with gate:
            start = time.perf_counter()
            answer = await call(client)
            took.append((time.perf_counter() - start) * 1000)
            return answer.status_code

    codes = await asyncio.gather(*(one() for _ in range(n)))
    took.sort()
    return codes, statistics.median(took), took[int(len(took) * 0.95) - 1]
```

In-process figures leave out the network and the server's workers; they compare two versions of
the code, they do not measure capacity. For that, run the server and use `adversarial_runner.py`
or load-sim.
