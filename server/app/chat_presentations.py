"""Use the Channel presentation renderer without Channel persistence."""
from agents import RunItemStreamEvent


class MemoryTransport:
    async def send_text(self, value): pass
    async def send_json(self, value): pass


def private_presenter(session):
    from app.utils import WebsocketHelper
    if session.presenter is None:
        session.presenter = WebsocketHelper(MemoryTransport(), session.history, session.agent,
                                             session.session_id, team_agent_id=session.team_id,
                                             persist_analytics=False)
        session.presenter.answers.enabled = True
        session.presenter.discovery.enabled = True
    session.presenter.history = session.history.copy()
    session.presenter.latest_agent = session.agent
    return session.presenter


async def present_result(presenter, output):
    for item in output.new_items:
        await presenter.handle_new_item(RunItemStreamEvent(name='tool_output', item=item))
    await presenter.text_output_complete(output, is_done=True)
    return current_turn_presentations(presenter, output.new_items)


def current_turn_presentations(presenter, new_items=()):
    # Channel sends the whole transcript; an HTTP reply represents one turn.
    # Keep historical surfaces in the presenter for actions, not in each reply.
    current_ids = set()
    for event in new_items:
        item = event.to_input_item()
        current_ids.update(value for value in (item.get('id'), item.get('call_id')) if value)
    for item in reversed(presenter.history):
        if item.get('role') == 'user':
            break
        current_ids.update(value for value in (item.get('id'), item.get('call_id')) if value)
    surfaces = {**presenter.answers.snapshots, **presenter.discovery.snapshots}
    return ({key: value for key, value in presenter.presentations.items() if key in current_ids},
            {key: value for key, value in surfaces.items() if key in current_ids})
