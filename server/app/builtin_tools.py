"""Builtin identities and team-scoped aliases, independent of registry row IDs."""
import json
import logging
from sqlalchemy import text
from app.orm_models import Tool, TeamToolAssignment

BUILTINS = {
    'DateTimeTool': {'description': 'Get current server date and time with timezone'},
    'WebSearchTool': {'description': 'Search the web for information'},
}
REGISTRY_LOCK = 734916203110
STARTUP_LOCK = 734916203111


def sequential_registry(db):
    # Scope planner changes to this transaction while the name index is suspect.
    if db.bind.dialect.name == 'postgresql':
        for setting in ('enable_indexscan', 'enable_indexonlyscan', 'enable_bitmapscan'):
            db.execute(text(f'SET LOCAL {setting} = off'))
    return db.query(Tool).order_by(Tool.id).all()


def lock_registry(db):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': REGISTRY_LOCK})


def aliases(tools):
    result, groups = {}, {}
    for tool in sorted(tools, key=lambda row: row.id):
        if tool.type == 'builtin' and tool.name in BUILTINS:
            groups.setdefault(tool.name, []).append(tool)
    for name, rows in groups.items():
        for field in ('config', 'owner_team_agent_id', 'visibility'):
            values = {json.dumps((row.config or {}) if field == 'config' else getattr(row, field),
                                 sort_keys=True, ensure_ascii=False) for row in rows}
            if len(values) > 1:
                raise ValueError(f'Conflicting builtin {field} for {name}; repair the registry before saving')
        result.update({row.id: rows[0].id for row in rows})
    return result


def normalize_agent_tool_ids(db, tool_ids, team_id):
    from app.database import _tool_available_to_team
    rows = sequential_registry(db)
    requested = set(tool_ids)
    if team_id is not None and any(not _tool_available_to_team(db, ident, team_id) for ident in requested):
        raise ValueError('One or more tools are not available to this Team Agent')
    available = [row for row in rows if team_id is None or _tool_available_to_team(db, row.id, team_id)]
    mapping = aliases(available)
    ids = {mapping.get(ident, ident) for ident in requested}
    clock = next((row for row in available if row.type == 'builtin' and row.name == 'DateTimeTool'), None)
    if clock:
        ids.add(mapping[clock.id])
    return sorted(ids)


def runtime_tools(rows):
    """Runtime has one implementation per builtin name, even before data repair."""
    seen = set()
    for row in sorted(rows, key=lambda value: value.get('id', 2**63)):
        name = row.get('name')
        if name in BUILTINS:
            if name in seen:
                logging.getLogger(__name__).warning('Ignoring duplicate builtin binding: %s', name)
                continue
            seen.add(name)
        yield row


def ensure_builtin_tools(db, owner_id, creator_id):
    lock_registry(db)
    rows = sequential_registry(db)
    for name, config in BUILTINS.items():
        existing = [row for row in rows if row.name == name]
        if existing:
            if any(row.type != 'builtin' for row in existing):
                raise ValueError(f'Reserved builtin name has a different tool type: {name}')
            if len(existing) > 1:
                logging.getLogger(__name__).warning('Duplicate builtin registry rows require migration: %s', name)
            continue
        tool = Tool(name=name, type='builtin', config=config, owner_team_agent_id=owner_id,
                    visibility='global', created_by_admin_id=creator_id)
        db.add(tool)
        db.flush()
        if owner_id is not None:
            db.add(TeamToolAssignment(team_agent_id=owner_id, tool_id=tool.id, relationship='owned'))
