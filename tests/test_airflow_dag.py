"""Parses the BigKinds inbox DAG. Skipped where Airflow is not installed (local venv, CI)."""
from pathlib import Path
import unittest

try:
    from airflow.models import DagBag
except ImportError:
    DagBag = None

DAG_FOLDER = Path(__file__).resolve().parents[1] / 'airflow' / 'dags'


@unittest.skipIf(DagBag is None, 'apache-airflow is not installed')
class DagParseTests(unittest.TestCase):
    def test_bigkinds_import_dag_loads(self):
        bag = DagBag(dag_folder=str(DAG_FOLDER), include_examples=False)
        self.assertEqual(bag.import_errors, {})
        dag = bag.get_dag('deepnews_bigkinds_import')
        self.assertIsNotNone(dag)
        command = dag.get_task('import_bigkinds_inbox').bash_command
        self.assertIn('backend.run_bigkinds_import --inbox', command)
        self.assertNotIn('run_ingestion', command)


if __name__ == '__main__':
    unittest.main()
