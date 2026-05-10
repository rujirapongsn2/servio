# Multi Team Agent Design Plan

## Goal

Servio should support multiple Team Agents. A Team Agent is a deployable agent team that owns its own starting agent, member agents, handoff graph, channels, users, active sessions, API keys, and analytics scope.

The current system is mostly global:

- `agents`, `agent_handoffs`, and `agent_tools` define one global agent graph.
- `tools` are global and visible to every agent/admin.
- `channel_configs` are global per channel type.
- `api_keys` are global and drive widget access.
- `session_manager` keeps active sessions globally in memory.
- `conversations` and analytics are global.
- Admin users are global.

The target design is to introduce `team_agents` as the primary tenant/workspace boundary while preserving backward compatibility for existing installs.

## Terminology

- `Team Agent`: A named workspace/team that groups multiple agents into one deployable service.
- `Starting Agent`: The entry agent for a Team Agent. It replaces the current global `is_starting_agent` behavior at runtime.
- `Member Agent`: Any agent assigned to a Team Agent and available for handoff.
- `Channel Assignment`: The mapping between a Team Agent and a channel instance such as Web Widget, LINE Messaging, Facebook Messaging, or future channels.
- `Team User`: Admin/operator user scoped to one or more Team Agents.
- `Active Session`: A live user conversation scoped to one Team Agent and channel.

## Core Product Requirements

1. Admin can create multiple Team Agents.
2. Each Team Agent can contain multiple existing-style Agents.
3. Each Team Agent has exactly one active Starting Agent.
4. Agents can either be exclusive to one Team Agent or reusable across teams. The first implementation should use membership mapping instead of duplicating agent rows.
5. Each Team Agent can enable and configure Channels independently.
6. Web Widget/API keys must resolve to a Team Agent.
7. LINE/Facebook webhook handling must route incoming messages to the correct Team Agent.
8. Online Agent must show active sessions grouped and filterable by Team Agent.
9. Analytics Dashboard must filter and aggregate by Team Agent.
10. Users and permissions must support access limited to selected Team Agents.
11. Each Team Agent can manage its own Tools.
12. A Team Agent can choose to share a Tool globally.
13. By default, admins should see only Tools owned by or available to the selected Team Agent, not every Tool in the system.

## Recommended Data Model

### New Tables

#### `team_agents`

Primary entity for the feature.

Suggested columns:

- `id`: integer primary key
- `name`: string, required
- `slug`: string, unique, required; used in URLs and public references
- `description`: text nullable
- `status`: string enum-like, default `active`; values `active`, `archived`
- `default_channel_type`: string nullable; optional UI convenience
- `created_at`: datetime
- `updated_at`: datetime

Indexes:

- unique index on `slug`
- index on `status`

#### `team_agent_members`

Maps Agents into a Team Agent.

Suggested columns:

- `team_agent_id`: FK `team_agents.id`, cascade delete
- `agent_id`: FK `agents.id`, cascade delete
- `role`: string, default `member`; values `starting`, `member`
- `sort_order`: integer default `0`
- `created_at`: datetime

Constraints:

- primary key `(team_agent_id, agent_id)`
- one starting agent per team via partial unique index where `role = 'starting'`

Rationale: Avoid adding `team_agent_id` directly to `agents` at first. Existing agents remain reusable, and migration is simpler.

#### `team_channel_configs`

Replaces global `channel_configs` for team-scoped channels. Keep existing `channel_configs` only for migration/fallback.

Suggested columns:

- `id`: integer primary key
- `team_agent_id`: FK `team_agents.id`, cascade delete
- `type`: string; `web_widget`, `line`, `facebook`, future values
- `name`: string
- `config`: JSON
- `is_active`: boolean default false
- `created_at`: datetime
- `updated_at`: datetime

Constraints:

- unique `(team_agent_id, type)`

Channel config examples:

- `web_widget`: `{ "theme": {}, "default_type": "chat", "allow_toggle": true }`
- `line`: `{ "channel_id": "", "channel_secret": "", "channel_access_token": "", "webhook_url": "/api/public/teams/{team_slug}/channels/line/webhook" }`
- `facebook`: `{ "page_id": "", "app_id": "", "app_secret": "", "page_access_token": "", "verify_token": "", "webhook_url": "/api/public/teams/{team_slug}/channels/facebook/webhook" }`

#### `team_user_memberships`

Maps admin users to Team Agents with roles.

Suggested columns:

- `admin_id`: FK `admins.id`, cascade delete
- `team_agent_id`: FK `team_agents.id`, cascade delete
- `role`: string; values `owner`, `admin`, `operator`, `viewer`
- `created_at`: datetime

Constraints:

- primary key `(admin_id, team_agent_id)`

Role guidance:

- `owner`: manage team, channels, users, destructive actions
- `admin`: manage agents, channels, API keys
- `operator`: monitor sessions, manual replies
- `viewer`: view analytics and sessions read-only

#### `team_tool_assignments`

Maps Tools into Team Agents and defines ownership/visibility.

Suggested columns:

- `team_agent_id`: FK `team_agents.id`, cascade delete
- `tool_id`: FK `tools.id`, cascade delete
- `relationship`: string, default `owned`; values `owned`, `shared_in`
- `created_at`: datetime

Constraints:

- primary key `(team_agent_id, tool_id)`
- index on `tool_id`

Rationale:

- `owned`: Tool was created by this Team Agent and is editable by team admins/owners.
- `shared_in`: Tool is globally shared by another team and visible/selectable in this team, but not editable except by the owning team or super admin.

This keeps Tool reuse explicit and prevents accidental cross-team leakage.

### Existing Tables To Extend

#### `api_keys`

Add:

- `team_agent_id`: nullable FK `team_agents.id`
- `channel_type`: string default `web_widget`

Behavior:

- New keys must always have `team_agent_id`.
- Existing keys with null `team_agent_id` should map to the default migrated Team Agent.
- `slug` remains useful for shareable links, but it must resolve to a team.

#### `conversations`

Add:

- `team_agent_id`: nullable FK `team_agents.id`, indexed
- `channel_type`: string nullable, indexed
- `channel_user_id`: string nullable; LINE user id, Facebook sender id, phone number, or widget session id
- `api_key_id`: nullable FK `api_keys.id`

Behavior:

- All new conversations should write `team_agent_id`.
- Analytics queries must filter by `team_agent_id`.
- Historical rows with null `team_agent_id` belong to the default migrated Team Agent for display.

#### `tools`

Add:

- `owner_team_agent_id`: nullable FK `team_agents.id`, indexed
- `visibility`: string default `team`; values `team`, `global`
- `created_by_admin_id`: nullable FK `admins.id`
- `updated_at`: datetime, if not already present

Behavior:

- New Tools created from a selected Team Agent default to `owner_team_agent_id = selected team` and `visibility = team`.
- A team owner/admin can change one of their Tools from `team` to `global`.
- `global` Tools are visible and selectable by all teams.
- Only the owning team owner/admin or super admin can edit/delete the Tool definition.
- Other teams can attach a global Tool to their agents but cannot mutate the Tool's config.
- If a global Tool is changed, all teams using it receive the updated definition. This should be explicit in the UI.

Default visibility rule:

- Tool list for a selected team returns:
  - Tools where `owner_team_agent_id = selected_team_id`
  - Tools where `visibility = global`
  - Optional built-in system Tools
- Tool list does not return private Tools owned by other teams.

#### `conversation_messages`

Optional but recommended:

- `team_agent_id`: nullable FK `team_agents.id`, indexed

Rationale: Redundant scope improves query performance and simplifies future partitioning. If not added, messages can be scoped via join to `conversations`.

#### `admins`

Keep global identity table. Do not duplicate users per Team Agent. Use memberships for authorization.

Add optional columns later:

- `display_name`
- `email`
- `is_super_admin`
- `last_login_at`

## Runtime Routing Design

### Team Context Resolution

Every inbound conversation must resolve `team_agent_id` before selecting the runtime starting agent.

Resolution rules:

1. Web Widget websocket `/ws?api_key=...`
   - Validate API key.
   - Load `api_keys.team_agent_id`.
   - If null, fall back to default Team Agent.
   - Set session team context.

2. Shareable Link `/c/{slug}`
   - Resolve `api_keys.slug` to API key.
   - Resolve `team_agent_id` from that key.

3. LINE webhook
   - Prefer URL: `/api/public/teams/{team_slug}/channels/line/webhook`.
   - Resolve `team_slug` to `team_agent_id`.
   - Load `team_channel_configs` where `type = 'line'`.

4. Facebook webhook
   - Prefer URL: `/api/public/teams/{team_slug}/channels/facebook/webhook`.
   - Resolve `team_slug` to `team_agent_id`.
   - Load team-specific verify token and page access token.

5. Future channels
   - Follow the same team slug or API key resolution pattern.

### Runtime Agent Graph

Current runtime uses `get_runtime_starting_agent()` globally. Introduce:

```python
get_runtime_starting_agent(team_agent_id: int)
```

Expected behavior:

- Load Team Agent members.
- Identify the member with `role = 'starting'`.
- Build handoffs using only agents that are members of the same Team Agent.
- Prevent cross-team handoffs unless explicitly allowed in future.
- Continue using existing Agent, Tool, LLM Provider models.

### Session Manager

Extend `SessionInfo` with:

- `team_agent_id`
- `team_agent_name`
- `channel_type`
- `channel_user_id`
- `api_key_id`

Extend methods:

- `connect(..., team_agent_id, channel_type, channel_user_id=None, api_key_id=None)`
- `get_all_sessions(team_agent_id: Optional[int] = None)`
- `get_intent_statistics(team_agent_id: Optional[int] = None)`

Online Agent UI should group by Team Agent and support filter modes:

- All teams the current user can access
- Specific Team Agent
- Channel type within Team Agent

## API Design

### Team Agent Management

Add admin endpoints:

- `GET /api/admin/team-agents`
- `POST /api/admin/team-agents`
- `GET /api/admin/team-agents/{team_id}`
- `PUT /api/admin/team-agents/{team_id}`
- `DELETE /api/admin/team-agents/{team_id}` or archive instead of hard delete

Payload shape:

```json
{
  "id": 1,
  "name": "Sales Support",
  "slug": "sales-support",
  "description": "Handles sales and product inquiries",
  "status": "active",
  "starting_agent_id": 12,
  "member_agent_ids": [12, 15, 18]
}
```

### Team Agent Members

Add endpoints:

- `GET /api/admin/team-agents/{team_id}/agents`
- `PUT /api/admin/team-agents/{team_id}/agents`
- `PUT /api/admin/team-agents/{team_id}/starting-agent`

Validation:

- Starting agent must be a member.
- Handoff graph shown in UI should only include same-team agents.
- If an agent is removed from team, remove invalid same-team handoff edges or mark them invalid.

### Team Tools

Add endpoints:

- `GET /api/admin/team-agents/{team_id}/tools`
- `POST /api/admin/team-agents/{team_id}/tools`
- `GET /api/admin/team-agents/{team_id}/tools/{tool_id}`
- `PUT /api/admin/team-agents/{team_id}/tools/{tool_id}`
- `DELETE /api/admin/team-agents/{team_id}/tools/{tool_id}`
- `PUT /api/admin/team-agents/{team_id}/tools/{tool_id}/visibility`
- `POST /api/admin/team-agents/{team_id}/tools/{tool_id}/attach`
- `DELETE /api/admin/team-agents/{team_id}/tools/{tool_id}/detach`

Query behavior:

- Default `GET /tools` returns only selected-team Tools, global Tools, and built-in system Tools.
- `?scope=team` returns only Tools owned by selected team.
- `?scope=global` returns only global Tools visible to all teams.
- `?scope=all` requires super admin.

Mutation rules:

- Creating a Tool from a team creates a team-private Tool by default.
- Team admins/owners can edit/delete Tools owned by that team.
- Team admins/owners can switch owned Tools between `team` and `global` visibility.
- Non-owning teams can attach global Tools to their agents but cannot edit/delete the Tool definition.
- Deleting a global Tool should require confirmation and should either detach it from all agents or be blocked while in use.

Legacy endpoint behavior:

- Current `/api/admin/tools` should accept `?team_agent_id=` during transition.
- Without `team_agent_id`, it should return Tools for the Default Team, not all private Tools.

### Team Channels

Add endpoints:

- `GET /api/admin/team-agents/{team_id}/channels`
- `GET /api/admin/team-agents/{team_id}/channels/{channel_type}`
- `PUT /api/admin/team-agents/{team_id}/channels/{channel_type}`

Replace current global channel calls gradually. The current endpoints can remain as deprecated aliases against the default Team Agent.

### Team API Keys

Add endpoints or query filters:

- `GET /api/admin/team-agents/{team_id}/api-keys`
- `POST /api/admin/team-agents/{team_id}/api-keys`
- `PUT /api/admin/team-agents/{team_id}/api-keys/{key_id}`
- `DELETE /api/admin/team-agents/{team_id}/api-keys/{key_id}`

The current `/api/admin/api-keys` can support `?team_agent_id=` during transition.

### Online Sessions

Update endpoint:

- `GET /api/admin/sessions?team_agent_id=all|{id}`

Return additional fields:

```json
{
  "session_id": "...",
  "team_agent_id": 1,
  "team_agent_name": "Sales Support",
  "channel_type": "web_widget",
  "source": "text_widget",
  "mode": "AI",
  "last_message_preview": "..."
}
```

### Analytics

Update endpoints with team filter:

- `GET /api/admin/analytics/summary?team_agent_id=...&period=week`
- `GET /api/admin/analytics/trends?team_agent_id=...&period=month`
- `GET /api/admin/analytics/conversations?team_agent_id=...`
- `GET /api/admin/analytics/conversations/{id}` must authorize team access from conversation team.

`team_agent_id=all` should be allowed only for super admin or users with access to multiple teams.

### User Management

Add endpoints:

- `GET /api/admin/users`
- `POST /api/admin/users`
- `PUT /api/admin/users/{admin_id}`
- `DELETE /api/admin/users/{admin_id}` or deactivate
- `GET /api/admin/team-agents/{team_id}/users`
- `PUT /api/admin/team-agents/{team_id}/users/{admin_id}`
- `DELETE /api/admin/team-agents/{team_id}/users/{admin_id}`

Access policy:

- Super admin sees all teams and users.
- Team owner/admin sees only users assigned to teams they own/admin.
- Operator can only monitor and reply for assigned teams.
- Viewer can only view analytics/sessions for assigned teams.

## Frontend Navigation And UX

### New Admin Sections

Recommended sidebar structure:

- Dashboard
- Team Agents
- Agents
- Channels
- Online Agent
- Analytics
- Users
- Settings

### Team Selector

Add persistent Team Agent selector near the admin header.

Modes:

- Specific team selected
- All teams, if authorized

Behavior:

- Agents page filters or badges agents by team membership.
- Tools page defaults to selected-team Tools plus global Tools.
- Channels page edits channels for selected team.
- Online Agent groups sessions by team by default.
- Analytics filters by selected team by default.
- Users page manages team membership for selected team.

### Team Agents Page

Capabilities:

- Create/edit/archive Team Agent.
- Assign member agents.
- Choose starting agent.
- Show handoff graph limited to team members.
- Show owned Tool count and global Tool usage count.
- Show channel status badges: Web Widget, LINE, Facebook.
- Show quick metrics: active sessions, conversations today, resolution rate.

### Tools Page

Current Tools UI should become team-aware.

Changes:

- Default view shows Tools available to the selected Team Agent only.
- Add filters: `Team Tools`, `Global Tools`, `Built-in/System`, and `All` for super admin only.
- Tool cards should display ownership:
  - `Owned by this team`
  - `Global shared`
  - `Owned by {team_name}`
  - `System`
- Tool create flow defaults to private team scope.
- Tool edit button is enabled only when the selected team owns the Tool or the user is super admin.
- Add a `Share globally` toggle for owned Tools.
- Add explicit warning when sharing globally because changes affect every team that uses that Tool.
- In Agent edit screens, the Tool selector should only list selected-team Tools, global Tools, and system Tools.
- Prevent selecting private Tools owned by other teams.

### Channels Page

Current Channels UI can be reused but must receive `team_agent_id`.

Changes:

- Card selection remains Web Widget, LINE, Facebook.
- API key manager is scoped to selected Team Agent.
- LINE/Facebook forms read/write `team_channel_configs`.
- Webhook URL includes team slug.
- Display warning if no Starting Agent is configured for the team.

### Online Agent Page

Changes:

- Add team grouping headers.
- Add team filter dropdown.
- Session card displays `team_agent_name` and `channel_type`.
- Manual mode authorization checks role per team.
- Admin monitor websocket must include token and session id; backend must reject if user lacks team access.

### Analytics Page

Changes:

- Add team filter dropdown and channel filter.
- Summary cards should clearly state scope.
- Conversation table includes Team Agent and Channel columns.
- Conversation detail should show team, channel, API key name, and channel user id.

### Users Page

New UI:

- User list with assigned teams and role badges.
- Invite/create user flow.
- Per-team role management.
- Disable/deactivate user.

## Migration Plan

### Phase 1: Add Team Model Without Behavior Change

1. Add `team_agents` and `team_agent_members`.
2. Create default Team Agent during database initialization, e.g. `Default Team` with slug `default`.
3. Add all existing agents to Default Team.
4. Set current global starting agent as Default Team starting member.
5. Add `team_agent_id` nullable columns to `api_keys`, `conversations`, and optionally `conversation_messages`.
6. Backfill existing API keys and conversations to Default Team.

Acceptance criteria:

- Existing `/admin/agents`, `/admin/tools/channels`, `/widget`, `/c/{slug}`, and `/ws` continue working.
- No existing API keys break.

### Phase 2: Team-Scoped Runtime

1. Implement `get_runtime_starting_agent(team_agent_id)`.
2. Update WebSocket API key validation to return API key data including `team_agent_id`.
3. Store team context in `SessionInfo`.
4. Write `team_agent_id` to new conversations.
5. Update messaging `handle_message(channel_type, user_id, text, team_agent_id)`.
6. Add team-scoped LINE/Facebook webhook URLs.

Acceptance criteria:

- Two teams can run different starting agents at the same time.
- Web Widget sessions route to the correct team based on API key.
- LINE/Facebook webhooks route using team slug.

### Phase 3: Team-Scoped Tools

1. Add `owner_team_agent_id`, `visibility`, `created_by_admin_id`, and `updated_at` to `tools`.
2. Add `team_tool_assignments`.
3. Backfill existing custom Tools to Default Team with `visibility = team`.
4. Treat existing built-in Tools as system/global Tools.
5. Update Tools API to filter by selected Team Agent by default.
6. Update Agent create/edit Tool selector to show only team-available Tools.
7. Add `Share globally` and ownership UI.

Acceptance criteria:

- Team A sees its private Tools, global Tools, and system Tools.
- Team A does not see Team B private Tools.
- Team A can share an owned Tool globally.
- Team B can attach Team A's global Tool but cannot edit/delete it.
- Existing agents keep their Tool assignments after migration.

### Phase 4: Team-Scoped Channels And API Keys

1. Add `team_channel_configs`.
2. Migrate current `channel_configs` to Default Team.
3. Update Channels UI to use selected Team Agent.
4. Scope API key CRUD to Team Agent.
5. Keep legacy global endpoints as aliases for Default Team until frontend migration is complete.

Acceptance criteria:

- Team A can enable LINE while Team B keeps LINE inactive.
- Team A and Team B can have different Facebook verify tokens.
- Shareable links generated from different teams route to different agent teams.

### Phase 5: Online Agent Grouping

1. Extend sessions API to filter by `team_agent_id`.
2. Extend monitor UI with team grouping and filter.
3. Enforce authorization on session list and session websocket.
4. Show channel source and team on each session card.

Acceptance criteria:

- Active sessions show under correct Team Agent.
- Operator assigned to Team A cannot see Team B sessions.
- Manual response works only for authorized operator/admin.

### Phase 6: Analytics Scoping

1. Add `team_agent_id` filters to summary, trends, conversation list, and detail endpoints.
2. Backfill historical conversations to Default Team.
3. Add Team Agent and Channel filters to Analytics UI.
4. Update dashboard charts to handle `all teams` and single team scopes.

Acceptance criteria:

- Analytics totals differ correctly by selected Team Agent.
- Conversation detail authorization prevents cross-team access.
- Existing historical analytics remains visible under Default Team.

### Phase 7: User Management

1. Add `team_user_memberships`.
2. Add user management endpoints.
3. Add authorization helper functions:
   - `require_super_admin`
   - `require_team_access(team_agent_id, min_role)`
   - `get_accessible_team_ids(current_user)`
4. Add Users admin page.
5. Gate Team Agent, Channel, Session, and Analytics endpoints by role.

Acceptance criteria:

- User can be assigned to one or many Team Agents.
- Role controls actions per team.
- Super admin can see all teams.

## Authorization Model

Use global identity plus team memberships.

Suggested role order:

1. `viewer`
2. `operator`
3. `admin`
4. `owner`
5. `super_admin`

Endpoint policy examples:

- View analytics: `viewer+`
- Monitor sessions: `operator+`
- Manual reply: `operator+`
- Manage channels/API keys: `admin+`
- Manage agents in team: `admin+`
- Create private team Tools: `admin+`
- Edit/delete owned team Tools: `admin+`
- Share owned Tools globally: `admin+` or stricter `owner+` if the UI needs stronger governance
- Attach global Tools to team agents: `admin+`
- Edit/delete global Tools owned by another team: `super_admin` only
- Manage team users: `owner+`
- Delete/archive team: `owner` or `super_admin`

## Backward Compatibility

Compatibility is important because existing URLs and API keys are already in use.

Keep these behaviors during migration:

- `/ws?api_key=...` still works.
- `/c/{slug}` still works.
- `/api/admin/channel-configs` still works as Default Team alias until frontend is fully migrated.
- Existing conversations remain queryable.
- Existing global starting agent becomes Default Team starting agent.

Deprecation path:

1. Add new team-scoped endpoints.
2. Move frontend to new endpoints.
3. Keep old endpoints for one or two releases.
4. Remove or hard-deprecate old endpoints only after update path is proven.

## Risk Areas

### Cross-Team Handoff Leakage

Risk: Runtime handoffs may include agents from other teams.

Mitigation:

- Build runtime handoff graph from `team_agent_members` only.
- Add backend validation when editing handoffs.
- Add tests for two teams with overlapping and non-overlapping agents.

### Channel Ambiguity

Risk: LINE/Facebook inbound webhooks have no API key and need deterministic team routing.

Mitigation:

- Use team slug in webhook URL.
- Store per-team channel credentials.
- Reject inactive or missing config early.

### Analytics Data Leakage

Risk: Conversation detail endpoint could expose another team's data.

Mitigation:

- Every analytics endpoint must authorize against `conversations.team_agent_id`.
- Never rely only on frontend filtering.

### Private Tool Leakage

Risk: A team may see or attach another team's private Tools.

Mitigation:

- Tool queries must always filter by selected team and visibility.
- Agent Tool assignment validation must reject private Tools owned by other teams.
- UI should clearly label Tool ownership and disable mutation actions for non-owned global Tools.
- Add tests for Team A private Tool not visible to Team B.

### Legacy Null `team_agent_id`

Risk: Old records without team id break filters.

Mitigation:

- Backfill during migration.
- Query helpers should coalesce null to Default Team only during transition.

### In-Memory Sessions

Risk: `session_manager` is process-local and not durable.

Mitigation:

- Keep in-memory for first phase.
- Store team context in session info.
- Future production scaling should move active session registry to Redis or database-backed presence.

## Testing Strategy

### Unit Tests

- Team creation and default team migration.
- Starting agent validation.
- Runtime graph generation per team.
- Tool visibility filtering per team.
- Tool ownership and global sharing permission checks.
- Channel config CRUD scoped by team.
- API key validation returns correct team.
- Authorization helper role checks.

### Integration Tests

- Web Widget websocket routes to correct team by API key.
- LINE webhook route with team slug loads correct channel config.
- Facebook verify token differs per team.
- Team-private Tools are hidden from other teams.
- Global Tools are attachable by other teams but not editable by non-owners.
- Sessions API returns only accessible team sessions.
- Analytics summary filters by team.

### Manual QA

1. Create Team A and Team B.
2. Assign different starting agents.
3. Generate widget API key for each team.
4. Create a private Tool in Team A and confirm Team B cannot see it.
5. Share the Team A Tool globally and confirm Team B can attach but not edit it.
6. Open both shareable links and confirm different agent behavior.
7. Enable LINE for Team A only and confirm Team B stays inactive.
8. Confirm Online Agent groups sessions by team.
9. Confirm Analytics can switch between Team A, Team B, and All.
10. Create an operator assigned only to Team A and confirm Team B is hidden.

## Suggested Implementation Order

1. Database schema and default team migration.
2. Backend team CRUD and membership APIs.
3. Team-scoped Tools and global sharing.
4. Runtime team context for widget/API key flow.
5. Team-scoped channels and webhook URLs.
6. Admin Team Agents UI.
7. Tools UI migration to selected team.
8. Channels UI migration to selected team.
9. Online Agent grouping and authorization.
10. Analytics filtering and authorization.
11. User management UI and role enforcement.
12. Cleanup legacy global aliases after update path is stable.

## First Code Milestone

The first implementation milestone should be intentionally small:

- Add `team_agents` and `team_agent_members` models.
- Create Default Team on startup.
- Assign existing agents to Default Team.
- Assign existing custom Tools to Default Team.
- Treat existing built-in Tools as system/global Tools.
- Add `team_agent_id` to `api_keys` and `conversations`.
- Backfill existing rows to Default Team.
- Add `GET /api/admin/team-agents`.
- Add selected team dropdown in admin UI, initially defaulting to Default Team.

This milestone gives the system a stable team boundary without changing channel behavior yet.
