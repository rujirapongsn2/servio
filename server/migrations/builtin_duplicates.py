"""Explicit PostgreSQL audit/repair. Never loads application settings or .env files."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

NAMES = {'DateTimeTool', 'WebSearchTool'}
LOCK = 734916203110
TABLES = ('tools', 'agent_tools', 'team_tool_assignments', 'workflow_creation_receipts')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def private_write(path, value):
    path = Path(path)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def sequential(conn):
    for key, value in [('enable_seqscan', 'on'), ('enable_indexscan', 'off'),
                       ('enable_indexonlyscan', 'off'), ('enable_bitmapscan', 'off')]:
        conn.execute(text(f'SET LOCAL {key} = {value}'))


def table(conn, name, schema):
    quote = conn.dialect.identifier_preparer.quote
    return f'{quote(schema)}.{quote(name)}'


def snapshot(conn, schema):
    sequential(conn)
    present = inspect(conn).get_table_names(schema=schema)
    return {name: sorted(conn.execute(text(f'SELECT to_jsonb(t) FROM {table(conn,name,schema)} t')).scalars(),
                         key=lambda row: json.dumps(row, sort_keys=True))
            for name in TABLES if name in present}


def diagnostics(conn, schema):
    target = table(conn, 'tools', schema)
    indexes = [dict(row) for row in conn.execute(text('''
        SELECT c.relname AS name,i.indisunique,i.indisvalid,i.indisready,i.indislive,i.indnkeyatts,
               pg_get_expr(i.indexprs,i.indrelid) AS expressions,
               pg_get_indexdef(i.indexrelid) AS definition,pg_get_expr(i.indpred,i.indrelid) AS predicate,
               ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY AS k(num,ord)
                     JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.num ORDER BY k.ord) AS columns
        FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        WHERE i.indrelid=to_regclass(:target) ORDER BY c.relname
    '''), {'target': target}).mappings()]
    scans = {}
    for name in sorted(NAMES):
        sequential(conn)
        seq = sorted(conn.execute(text(f'SELECT id FROM {target} WHERE name=:name'), {'name': name}).scalars())
        conn.execute(text('SET LOCAL enable_seqscan = off'))
        conn.execute(text('SET LOCAL enable_indexscan = on'))
        indexed = sorted(conn.execute(text(f'SELECT id FROM {target} WHERE name=:name'), {'name': name}).scalars())
        plan = conn.execute(text(f'EXPLAIN (FORMAT JSON) SELECT id FROM {target} WHERE name=:name'), {'name': name}).scalar()
        scans[name] = {'sequential_ids': seq, 'index_preferred_ids': indexed, 'equal': seq == indexed, 'plan': plan}
    sequential(conn)
    database = dict(conn.execute(text('''SELECT current_database() AS database,version() AS version,
        d.datcollate,d.datctype,d.datcollversion,pg_database_collation_actual_version(d.oid) AS actual_version
        FROM pg_database d WHERE d.datname=current_database()''')).mappings().one())
    collations = [dict(row) for row in conn.execute(text('''SELECT a.attname,c.collname,c.collprovider,
        c.collisdeterministic,c.collversion,pg_collation_actual_version(c.oid) AS actual_version
        FROM pg_attribute a JOIN pg_collation c ON c.oid=a.attcollation
        WHERE a.attrelid=to_regclass(:target) AND a.attnum>0'''), {'target': target}).mappings()]
    amcheck = []
    available = conn.execute(text("SELECT to_regprocedure('bt_index_check(regclass,boolean)') IS NOT NULL")).scalar()
    if available:
        for index in indexes:
            try:
                with conn.begin_nested():
                    conn.execute(text('SELECT bt_index_check(CAST(:index AS regclass), true)'),
                                 {'index': table(conn, index['name'], schema)})
                amcheck.append({'index': index['name'], 'status': 'passed'})
            except Exception as error:
                amcheck.append({'index': index['name'], 'status': 'failed',
                                'sqlstate': getattr(getattr(error, 'orig', None), 'pgcode', None)})
    versions_match = (database['datcollversion'] is None or database['actual_version'] is None or database['datcollversion'] == database['actual_version']) and all(
        row['collversion'] is None or row['actual_version'] is None or row['collversion'] == row['actual_version'] for row in collations)
    return {'database': database, 'indexes': indexes, 'name_scans': scans, 'column_collations': collations, 'collation_versions_match': versions_match,
            'amcheck_available': bool(available), 'amcheck': amcheck,
            'name_uniqueness_enforced': any(index['columns'] == ['name'] and index['indnkeyatts'] == 1
                and not index['expressions'] and index['indisunique']
                and index['indisvalid'] and index['indisready'] and index['indislive'] and not index['predicate'] for index in indexes)}


def json_references(value, ids, key=''):
    if key in ('tool_id', 'tool_ids'):
        values = value if isinstance(value, list) else [value]
        if any(type(item) in (int, str) and str(item) in {str(ident) for ident in ids} for item in values):
            return True
    if key == 'tools' and isinstance(value, list):
        if any(isinstance(item, dict) and str(item.get('id')) in {str(ident) for ident in ids} for item in value):
            return True
    if isinstance(value, dict):
        return any(json_references(item, ids, name) for name, item in value.items())
    if isinstance(value, list):
        return any(json_references(item, ids, key) for item in value)
    return False


def references(conn, schema, ids):
    """Discover inbound FKs and semantic references, including non-FK JSON drafts."""
    inspector = inspect(conn)
    found, blockers = [], []
    for namespace in inspector.get_schema_names():
        if namespace in ('information_schema', 'pg_catalog') or namespace.startswith('pg_'):
            continue
        for name in inspector.get_table_names(schema=namespace):
            known = namespace == schema and name in TABLES
            for fk in inspector.get_foreign_keys(name, schema=namespace):
                if ids and fk['referred_table'] in TABLES[1:] and (fk.get('referred_schema') or namespace) == schema:
                    blockers.append(f'Unreviewed dependency on a rewritten link table: {namespace}.{name}.{fk["name"]}')
                if fk['referred_table'] != 'tools' or (fk.get('referred_schema') or namespace) != schema:
                    continue
                if fk['referred_columns'] != ['id'] or len(fk['constrained_columns']) != 1:
                    blockers.append(f'Unsupported composite FK: {namespace}.{name}.{fk["name"]}')
                    continue
                column = fk['constrained_columns'][0]
                quote = conn.dialect.identifier_preparer.quote
                rows = conn.execute(text(f'SELECT to_jsonb(t) FROM {table(conn,name,namespace)} t WHERE {quote(column)}=ANY(:ids)'), {'ids': list(ids)}).scalars().all() if ids else []
                found.append({'schema': namespace, 'table': name, 'constraint': fk['name'], 'columns': [column], 'references': len(rows)})
                if rows and not (known and name in ('agent_tools', 'team_tool_assignments') and column == 'tool_id'):
                    blockers.append(f'Unmapped foreign key references: {namespace}.{name}.{column}')
            columns = inspector.get_columns(name, schema=namespace)
            # Unknown application records are inspected without logging their contents.
            candidates = [col for col in columns if col['name'] in ('tool_id', 'tool_ids', 'resource_id', 'resource_kind')
                          or any(kind in str(col['type']).lower() for kind in ('json', 'text', 'char'))]
            if not candidates or not ids:
                continue
            quote = conn.dialect.identifier_preparer.quote
            selected = ','.join(quote(col['name']) for col in candidates)
            for row in conn.execute(text(f'SELECT {selected} FROM {table(conn,name,namespace)}')).mappings():
                if not known and row.get('resource_kind') == 'tool' and row.get('resource_id') in ids:
                    blockers.append(f'Unmapped polymorphic reference: {namespace}.{name}.resource_id')
                for col in candidates:
                    key, value = col['name'], row[col['name']]
                    if known and name in ('agent_tools', 'team_tool_assignments') and key == 'tool_id':
                        continue
                    if known and name == 'workflow_creation_receipts' and key == 'resource_id':
                        continue  # The full receipt is checked and remapped below.
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except ValueError:
                            continue
                    if json_references(value, ids, key):
                        blockers.append(f'Unmapped logical reference: {namespace}.{name}.{key}')
    if ids:
        dependent_views = conn.execute(text("""SELECT DISTINCT n.nspname,c.relname FROM pg_depend d
            JOIN pg_rewrite r ON r.oid=d.objid JOIN pg_class c ON c.oid=r.ev_class
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE d.refobjid=to_regclass(:target) AND c.relkind IN ('v','m')"""),
            {'target': table(conn,'tools',schema)}).all()
        blockers.extend(f'Unreviewed dependent view: {ns}.{name}' for ns,name in dependent_views)
        triggers = conn.execute(text("""SELECT t.tgname FROM pg_trigger t
            WHERE NOT t.tgisinternal AND t.tgenabled <> 'D'
            AND t.tgrelid IN (to_regclass(:tools),to_regclass(:agents),to_regclass(:teams),to_regclass(:receipts))"""),
            {'tools':table(conn,'tools',schema),'agents':table(conn,'agent_tools',schema),
             'teams':table(conn,'team_tool_assignments',schema),
             'receipts':table(conn,'workflow_creation_receipts',schema)}).scalars()
        blockers.extend(f'Unreviewed trigger: {name}' for name in triggers)
    return found, sorted(set(blockers))


def transform(before, canonical=None):
    canonical = canonical or {}
    if set(canonical) - NAMES or any(type(ident) is not int or ident <= 0 for ident in canonical.values()):
        raise ValueError('Canonical map must contain builtin names and positive integer IDs')
    groups, mapping, blockers = {}, {}, []
    for row in before['tools']:
        if row['name'] in NAMES:
            groups.setdefault(row['name'], []).append(row)
    for name, rows in groups.items():
        if any(row['type'] != 'builtin' for row in rows):
            blockers.append(f'Reserved name uses another tool type: {name}')
            continue
        if len(rows) < 2:
            if name in canonical and canonical[name] != rows[0]['id']:
                blockers.append(f'Canonical ID is not a member of {name}')
            continue
        # A single canonical row cannot represent different ownership or visibility scopes.
        for field in ('config', 'owner_team_agent_id', 'visibility'):
            if len({json.dumps(row.get(field) or ({} if field == 'config' else None), sort_keys=True) for row in rows}) > 1:
                blockers.append(f'Conflicting {field}: {name}')
        ident = canonical.get(name, min(row['id'] for row in rows))
        if ident not in {row['id'] for row in rows}:
            blockers.append(f'Canonical ID is not a member of {name}')
            continue
        mapping.update({row['id']: ident for row in rows if row['id'] != ident})
    tools = {row['id']: row for row in before['tools']}
    if any(row['tool_id'] not in tools for row in before.get('agent_tools', [])):
        blockers.append('Orphan agent tool reference')
    after = json.loads(json.dumps(before))
    after['tools'] = [row for row in after['tools'] if row['id'] not in mapping]
    merged = {}
    for row in after.get('agent_tools', []):
        row['tool_id'] = mapping.get(row['tool_id'], row['tool_id'])
        merged[(row['agent_id'], row['tool_id'])] = row
    after['agent_tools'] = list(merged.values())
    merged = {}
    for row in after.get('team_tool_assignments', []):
        original = tools.get(row['tool_id'])
        if original is None:
            blockers.append('Orphan team tool reference')
            merged[(row['team_agent_id'],row['tool_id'])] = row
            continue
        if row['tool_id'] in set(mapping) | set(mapping.values()):
            if row['relationship'] not in ('owned', 'shared_in'):
                blockers.append('Unknown team assignment relationship')
            if row['relationship'] == 'owned' and original['owner_team_agent_id'] != row['team_agent_id']:
                blockers.append('Owned assignment disagrees with the tool owner')
        row['tool_id'] = mapping.get(row['tool_id'], row['tool_id'])
        key = row['team_agent_id'], row['tool_id']
        if key in merged:
            old = merged[key]
            row['relationship'] = 'owned' if 'owned' in (row['relationship'], old['relationship']) else 'shared_in'
            row['created_at'] = min(row['created_at'], old['created_at'])
        merged[key] = row
    after['team_tool_assignments'] = list(merged.values())
    for row in after.get('workflow_creation_receipts', []):
        if row['resource_kind'] == 'tool':
            row['resource_id'] = mapping.get(row['resource_id'], row['resource_id'])
    after = {name: sorted(rows, key=lambda row: json.dumps(row, sort_keys=True)) for name, rows in after.items()}
    return mapping, after, blockers


def audit(conn, schema='public', canonical=None):
    before = snapshot(conn, schema)
    if not {'tools', 'agent_tools', 'team_tool_assignments'} <= before.keys():
        raise ValueError('Required registry tables are missing')
    mapping, after, blockers = transform(before, canonical)
    collisions = [dict(row) for row in conn.execute(text(f'SELECT name,count(*) AS count FROM {table(conn,"tools",schema)} GROUP BY name HAVING count(*)>1')).mappings()]
    blockers.extend('Unmapped duplicate tool name: ' + row['name'] for row in collisions if row['name'] not in NAMES)
    fks, blocked = references(conn, schema, set(mapping))
    evidence = diagnostics(conn, schema)
    tool_rows = {row['id']: row for row in before['tools']}
    for name, scans in evidence['name_scans'].items():
        if any(tool_rows[ident]['name'] != name for ident in scans['sequential_ids']):
            blockers.append(f'Collation-equal but byte-distinct builtin names: {name}')
    # Supported link tables must have exactly the shapes we can preserve.
    expected = {'agent_tools': {'agent_id', 'tool_id'}, 'team_tool_assignments': {'team_agent_id', 'tool_id', 'relationship', 'created_at'}}
    for name, columns in expected.items():
        primary = inspect(conn).get_pk_constraint(name, schema=schema)['constrained_columns']
        expected_pk = ['agent_id', 'tool_id'] if name == 'agent_tools' else ['team_agent_id', 'tool_id']
        if primary != expected_pk:
            blockers.append(f'Unexpected primary key in {name}')
        if {col['name'] for col in inspect(conn).get_columns(name, schema=schema)} != columns:
            blockers.append(f'Unexpected columns in {name}')
    return {'version': 1, 'schema': schema, 'before_digest': digest(before), 'after_digest': digest(after),
            'mapping': {str(key): value for key, value in mapping.items()}, 'canonical': canonical or {},
            'blockers': sorted(set(blockers + blocked)), 'duplicate_names': collisions, 'foreign_keys': fks, 'diagnostics': evidence}


def insert_records(conn, schema, name, rows):
    if rows:
        target = table(conn, name, schema)
        conn.execute(text(f'INSERT INTO {target} SELECT * FROM json_populate_recordset(NULL::{target}, CAST(:rows AS json))'), {'rows': json.dumps(rows)})


def replace_links(conn, schema, state, ids):
    for name in ('agent_tools', 'team_tool_assignments'):
        conn.execute(text(f'DELETE FROM {table(conn,name,schema)} WHERE tool_id=ANY(:ids)'), {'ids': list(ids)})
        insert_records(conn, schema, name, [row for row in state[name] if row['tool_id'] in ids])
    if 'workflow_creation_receipts' in state:
        target = table(conn, 'workflow_creation_receipts', schema)
        conn.execute(text(f"DELETE FROM {target} WHERE resource_kind='tool' AND resource_id=ANY(:ids)"), {'ids': list(ids)})
        insert_records(conn, schema, 'workflow_creation_receipts', [row for row in state['workflow_creation_receipts'] if row['resource_kind'] == 'tool' and row['resource_id'] in ids])


def maintenance_lock(conn, schema):
    conn.execute(text("SET LOCAL lock_timeout='10s'"))
    conn.execute(text("SET LOCAL statement_timeout='120s'"))
    conn.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': LOCK})
    # Lock every application table: unknown logical reference writers must also stop.
    inspector = inspect(conn)
    for namespace in sorted(inspector.get_schema_names()):
        if namespace in ('information_schema', 'pg_catalog') or namespace.startswith('pg_'):
            continue
        for name in sorted(inspector.get_table_names(schema=namespace)):
            conn.execute(text(f'LOCK TABLE {table(conn,name,namespace)} IN SHARE ROW EXCLUSIVE MODE'))
    sequential(conn)


def apply(conn, plan, backup):
    schema = plan['schema']
    maintenance_lock(conn, schema)
    current = snapshot(conn, schema)
    if digest(current) == plan['after_digest']:
        clean = audit(conn, schema)
        _, blockers = references(conn, schema, {int(key) for key in plan['mapping']})
        if clean['mapping'] or clean['blockers'] or blockers:
            raise ValueError('Expected clean state still has unresolved references or duplicates')
        return 'already_applied'
    if digest(current) != plan['before_digest']:
        raise ValueError('Plan is stale; run dry-run again')
    fresh = audit(conn, schema, plan['canonical'])
    if fresh['blockers'] or fresh['mapping'] != plan['mapping']:
        raise ValueError('Unsafe migration plan: ' + '; '.join(fresh['blockers']))
    mapping, after, _ = transform(current, plan['canonical'])
    if digest(after) != plan['after_digest']:
        raise ValueError('Plan after-state does not match the reviewed mapping')
    private_write(backup, {'version': 1, 'database': conn.execute(text('SELECT current_database()')).scalar(), 'schema': schema, 'before': current, 'after': after, 'mapping': plan['mapping']})
    ids = set(mapping) | set(mapping.values())
    replace_links(conn, schema, after, ids)
    conn.execute(text(f'DELETE FROM {table(conn,"tools",schema)} WHERE id=ANY(:ids)'), {'ids': list(mapping)})
    if snapshot(conn, schema) != after:
        raise ValueError('Post-migration validation failed; transaction rolled back')
    return 'applied'


def rollback(conn, backup):
    schema = backup['schema']
    if backup['database'] != conn.execute(text('SELECT current_database()')).scalar():
        raise ValueError('Backup database identity does not match')
    maintenance_lock(conn, schema)
    state = snapshot(conn, schema)
    if state == backup['before']:
        return 'already_restored'
    if state != backup['after']:
        raise ValueError('Database changed after migration; restore a full backup on an isolated copy instead')
    ids = {int(key) for key in backup['mapping']} | set(backup['mapping'].values())
    insert_records(conn, schema, 'tools', [row for row in backup['before']['tools'] if row['id'] in {int(key) for key in backup['mapping']}])
    replace_links(conn, schema, backup['before'], ids)
    if snapshot(conn, schema) != backup['before']:
        raise ValueError('Rollback validation failed; transaction rolled back')
    return 'restored'


def validation_errors(report):
    result = []
    evidence = report['diagnostics']
    if report['mapping'] or report['blockers']:
        result.append('duplicates or unmapped references remain')
    if not evidence['name_uniqueness_enforced']:
        result.append('no active nonpartial unique name index')
    if not evidence['collation_versions_match']:
        result.append('collation versions differ')
    if any(check['status'] == 'failed' for check in evidence['amcheck']):
        result.append('amcheck failed')
    if any(not scan['equal'] for scan in evidence['name_scans'].values()):
        result.append('sequential and index-preferred scans disagree')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['dry-run', 'apply', 'validate', 'rollback'])
    parser.add_argument('--url-env', default='SERVIO_BUILTIN_MIGRATION_URL')
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--allow-nonlocal', action='store_true')
    parser.add_argument('--schema', default='public')
    parser.add_argument('--canonical', type=Path, help='JSON mapping builtin name to reviewed canonical ID')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    url = make_url(os.environ[args.url_env])
    if url.get_backend_name() != 'postgresql' or url.database != args.expected_database:
        parser.error('Explicit PostgreSQL URL and matching expected database required')
    if url.host not in ('localhost', '127.0.0.1', '::1') and not args.allow_nonlocal:
        parser.error('Nonlocal connection requires --allow-nonlocal')
    engine = create_engine(url, connect_args={'connect_timeout': 5, 'application_name': 'servio_builtin_repair'})
    with engine.begin() as conn:
        if args.mode in ('dry-run', 'validate'):
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout='120s'"))
            conn.execute(text("SET LOCAL lock_timeout='10s'"))
        if conn.execute(text('SELECT current_database()')).scalar() != args.expected_database:
            raise ValueError('Connected database does not match expected database')
        if args.mode in ('dry-run', 'validate'):
            value = audit(conn, args.schema, json.loads(args.canonical.read_text()) if args.canonical else None)
            if args.output:
                private_write(args.output, value)
            print(json.dumps({'mode': args.mode, 'mapping': value['mapping'], 'blockers': value['blockers'], 'before_digest': value['before_digest']}))
            if args.mode == 'validate' and (errors := validation_errors(value)):
                raise ValueError('; '.join(errors))
        elif args.mode == 'apply':
            if not args.plan or not args.backup:
                parser.error('Apply requires --plan and a new --backup file')
            plan = json.loads(args.plan.read_text())
            if plan['diagnostics']['database']['database'] != args.expected_database:
                raise ValueError('Plan database identity does not match')
            outcome = apply(conn, plan, args.backup)
        else:
            if not args.backup:
                parser.error('Rollback requires --backup')
            outcome = rollback(conn, json.loads(args.backup.read_text()))
    engine.dispose()
    if args.mode in ("apply", "rollback"):
        print(outcome)


if __name__ == '__main__':
    try:
        main()
    except SQLAlchemyError as error:
        # Do not print bound parameters or DSNs in operator logs.
        code = getattr(getattr(error, 'orig', None), 'pgcode', None)
        raise SystemExit(f'Database operation failed (SQLSTATE {code}); transaction rolled back. See the protected audit/backup and database logs.') from None
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f'Migration stopped: {error}') from None
