"""Must run before any test module imports `main` (which calls db.init_db()
and starts the backup task at import time) — points the app at a throwaway
DB instead of the real dora.db, and disables the backup loop so tests don't
write snapshot files into the real backend directory."""
import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="dora_test_"), "test_dora.db")
