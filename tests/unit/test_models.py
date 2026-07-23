from src.db.models import RunRow
from src.db.session import create_db_session, init_db


def test_run_row_roundtrip():
    init_db()
    with create_db_session() as s:
        run = RunRow(input_text="hello", instruction="upper", status="running")
        s.add(run)
        s.commit()
        run_id = run.id
    with create_db_session() as s:
        row = s.get(RunRow, run_id)
        assert row is not None
        assert row.input_text == "hello"
        assert row.status == "running"
        assert row.created_at is not None
