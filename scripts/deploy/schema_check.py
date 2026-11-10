"""Read-only table/column preflight. Never initializes or migrates a database."""
import json
import os
from sqlalchemy import create_engine, inspect
from app.orm_models import Base

engine = create_engine(os.environ['DATABASE_URL'], connect_args={
    'connect_timeout': 10, 'options': '-c default_transaction_read_only=on -c statement_timeout=15000'})
missing = []
try:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            missing.append(table.name)
            continue
        columns = {column['name'] for column in inspector.get_columns(table.name)}
        missing.extend(f'{table.name}.{column.name}' for column in table.columns if column.name not in columns)
finally:
    engine.dispose()
if missing:
    print(json.dumps({'missing_schema': missing}))
    raise SystemExit('Schema requires a separately approved migration; deployment stopped')
print('Read-only schema preflight passed')
