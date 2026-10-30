"""Read-only channel inventory, scoped to accessible teams and excluding secrets."""
from datetime import datetime, timezone

from sqlalchemy import or_

from app.db_config import get_db
from app.orm_models import ApiKey, ChannelConfig

FIELDS = {
    'line': ('channel_id', 'channel_secret', 'channel_access_token'),
    'facebook': ('page_id', 'app_id', 'app_secret', 'page_access_token', 'verify_token'),
}


def channel_overview(username: str) -> list[dict]:
    from app import database
    teams = {team['id']: team for team in database.get_all_team_agents(username=username)}
    admin = database.get_admin_by_username(username)
    legacy = bool(admin and admin.get('is_super_admin'))
    editable = {team_id: database.has_team_access(username, team_id, 'admin') for team_id in teams}
    now = datetime.now(timezone.utc)
    rows = []

    def common(item):
        team = teams.get(item.team_agent_id)
        return dict(id=item.id, name=item.name, team_id=item.team_agent_id,
                    team_name=team['name'] if team else 'Legacy / unassigned',
                    team_active=team['status'] == 'active' if team else True,
                    can_edit=editable.get(item.team_agent_id, legacy),
                    is_active=item.is_active, updated_at=item.updated_at.isoformat() if item.updated_at else None)

    def visible(column):
        return or_(column.in_(list(teams)), column.is_(None)) if legacy else column.in_(list(teams))

    with get_db() as db:
        for key in db.query(ApiKey).filter(visible(ApiKey.team_agent_id)).all():
            row = common(key)
            expired = bool(key.expires_at and key.expires_at.replace(tzinfo=timezone.utc) <= now)
            row.update(kind='web', channel_type='web_widget' if key.channel_type in (None, 'web_widget', 'web-widget') else 'api',
                       status='expired' if expired else 'active' if key.is_active and row['team_active'] else 'paused',
                       slug=key.slug, allowed_domains=key.allowed_domains or [],
                       voice_response_enabled=key.voice_response_enabled,
                       expires_at=key.expires_at.isoformat() if key.expires_at else None,
                       usage_count=key.usage_count or 0)
            rows.append(row)
        for config in db.query(ChannelConfig).filter(visible(ChannelConfig.team_agent_id)).all():
            if config.type not in FIELDS:
                continue
            values = config.config or {}
            present = [field for field in FIELDS[config.type] if values.get(field)]
            # Auto-created empty defaults are not configured connections.
            if not present and not config.is_active:
                continue
            row = common(config)
            complete = len(present) == len(FIELDS[config.type])
            row.update(kind='messaging', channel_type=config.type,
                       status='incomplete' if not complete else 'active' if config.is_active and row['team_active'] else 'paused',
                       identifier=str(values.get('channel_id' if config.type == 'line' else 'page_id') or ''),
                       configured_fields=present, required_fields=list(FIELDS[config.type]))
            rows.append(row)
    return sorted(rows, key=lambda row: (row['team_name'].casefold(), row['name'].casefold(), row['id']))
