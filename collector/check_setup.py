import psycopg

from collector.config import DATABASE_URL


def check_db() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'"
        ).fetchall()
    print("DB OK, raw tables:", sorted(r[0] for r in rows))

if __name__ == "__main__":
    check_db()
