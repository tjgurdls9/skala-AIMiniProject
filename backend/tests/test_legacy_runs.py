"""Runs recorded before a starter was retired stay readable (read-only); new runs cannot use a retired starter."""
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.contracts import ROOT, DomainError
from backend.store import Store

READS = ('snapshot', 'acceptance_status', 'release_view', 'tool_calls')


def read_everything(store, run_id):
    for name in READS:
        getattr(store, name)(run_id)
    store.events(run_id, 0)


class LegacyRuns(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_a_run_whose_starter_no_longer_exists_is_still_readable_but_not_creatable(self):
        path = self.root / 'old.sqlite3'
        store = Store(path)
        project = store.project(dict(title='synthetic', request='합성 요청'))
        run = store.create_run(project['project_id'], dict(mode='live'), 'blank-v1')
        with sqlite3.connect(path) as db:                       # emulate a database written when this starter still existed
            db.execute('DROP TRIGGER run_templates_update_blocked')
            db.execute("UPDATE run_templates SET template_id='retired-starter-v1' WHERE run_id=?", (run['run_id'],))
        reopened = Store(path)
        read_everything(reopened, run['run_id'])
        with reopened.transaction() as db:
            self.assertEqual(reopened.template_id(db, run['run_id']), 'retired-starter-v1')
        with self.assertRaises(DomainError):
            reopened.create_run(project['project_id'], dict(mode='live'), 'retired-starter-v1')

    def test_preserved_runtime_databases_open_read_only_copies(self):
        sources = sorted((ROOT / 'runtime-data').glob('*.sqlite3'))
        if not sources:
            self.skipTest('no preserved runtime databases on this machine (they are not tracked)')
        for source in sources:
            copy = self.root / source.name                      # never open the original: Store creates tables and triggers
            shutil.copy(source, copy)
            store = Store(copy)
            with sqlite3.connect(copy) as db:
                run_ids = [row[0] for row in db.execute('SELECT id FROM runs')]
            for run_id in run_ids:
                read_everything(store, run_id)


if __name__ == '__main__':
    unittest.main()
