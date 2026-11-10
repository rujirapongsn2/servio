"""Shared tool authorization, evidence and secret handling for every runtime transport."""
from contextvars import ContextVar
import asyncio
import json
import logging
import re
from urllib.parse import quote, quote_plus, urlsplit, parse_qsl

from agents import RunHooks

activity: ContextVar[list | None] = ContextVar('private_tool_activity', default=None)
execution_lock: ContextVar[asyncio.Lock | None] = ContextVar('private_tool_lock', default=None)
log_secrets: ContextVar[set[str] | None] = ContextVar('private_log_secrets', default=None)
access_check: ContextVar[object] = ContextVar('runtime_access_check', default=None)
failed_writes: ContextVar[dict | None] = ContextVar('runtime_failed_writes', default=None)


def install_log_redaction():
    """Scrub records at creation, before handlers (including external SDK handlers)."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, '_servio_private_redaction', False):
        return
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        secrets = log_secrets.get()
        if secrets is not None:
            record.msg, record.args = redact(record.getMessage(), secrets), ()
            # Third-party tracebacks can contain request URLs or response bodies.
            record.exc_info, record.exc_text, record.stack_info = None, None, None
        return record
    factory._servio_private_redaction = True
    logging.setLogRecordFactory(factory)


class ToolExecutionFailed(Exception):
    """Stops the run without passing remote errors or speculative answers to the UI."""


def credential_values(agents):
    values = set()
    def collect(value, key=''):
        sensitive = re.search(r'token|password|secret|authorization|api[_-]?key|cookie|credential', key, re.I)
        if isinstance(value, dict):
            if isinstance(value.get('name'), str) and re.search(r'token|auth|key|cookie|secret', value['name'], re.I):
                collect(value.get('value'), 'secret')
            for name, child in value.items():
                collect(child, 'secret' if sensitive else name)
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
        elif isinstance(value, str) and value:
            if sensitive:
                values.add(value)
                if value.lower().startswith('bearer '):
                    values.add(value[7:])
            if key in ('endpoint', 'base_url'):
                parsed = urlsplit(value)
                values.update(part for part in (parsed.username, parsed.password) if part)
                for name, child in parse_qsl(parsed.query):
                    collect(child, name)
    for agent in agents:
        collect(agent.get('llm_provider') or {})
        for tool in agent.get('tools', []):
            collect(json.loads(tool.get('config') or '{}'))
    return {variant for value in values for variant in (value, quote(value, safe=''), quote_plus(value))}


def redact(value, secrets):
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        if value.startswith(('{', '[')):
            try:
                parsed = json.loads(value)
                return json.dumps(redact(parsed, secrets), ensure_ascii=False)
            except (ValueError, RecursionError):
                pass
        return value
    if isinstance(value, list):
        return [redact(child, secrets) for child in value]
    if isinstance(value, dict):
        return {key: '[REDACTED]' if re.search(r'token|password|secret|authorization|api[_-]?key|cookie|credential', key, re.I)
                else redact(child, secrets) for key, child in value.items()}
    return value


def failed_result(value):
    if not isinstance(value, str):
        return False
    try:
        data = json.loads(value)
        if isinstance(data, dict) and (data.get('isError') is True or data.get('success') is False
                                     or data.get('error') or data.get('status') in ('error', 'failed')):
            return True
    except ValueError:
        pass
    return value.lstrip().lower().startswith((
        'error calling ', 'error searching ', 'http error calling ', 'mcp error:', 'unsupported http method',
        'no tools available from mcp', 'requested tools not found', 'mcp tools are disabled',
        'knowledge not found or unavailable', 'table query failed', 'an error occurred while running the tool',
        "i apologize, but i'm having trouble accessing", 'knowledge search is temporarily unavailable'))


class AccessHooks(RunHooks):
    def __init__(self, check):
        self.check = check

    async def on_agent_start(self, context, agent):
        self.check()

    async def on_handoff(self, context, from_agent, to_agent):
        self.check()


def protect_tools(runtime_agents, captured, check=None):
    """No transport-specific prompts or reply replacement. Errors stay in SDK history."""
    secrets = credential_values(captured)
    for agent in runtime_agents:
        agent._servio_secrets = secrets
        for tool in agent.tools:
            if not hasattr(tool, 'on_invoke_tool') or getattr(tool, '_servio_guarded', False):
                continue
            tool._servio_guarded = True
            invoke, name = tool.on_invoke_tool, tool.name
            may_write = getattr(tool, '_servio_may_write', False)
            async def execute(context, arguments, invoke=invoke, name=name, may_write=may_write):
                current_check = access_check.get() or check
                if current_check:
                    current_check()
                entries = activity.get()
                entry = {'name': name, 'status': 'running'}
                if entries is not None:
                    entries.append(entry)
                ledger = failed_writes.get()
                # Altering arguments is not permission to repeat an uncertain
                # external write during this model run.
                key = name
                if may_write and ledger is not None and key in ledger:
                    entry['status'] = 'retry_blocked'
                    return ledger[key]
                try:
                    result = await invoke(context, arguments)
                    if failed_result(result):
                        raise ToolExecutionFailed()
                    current_secrets = secrets | (log_secrets.get() or set())
                    if isinstance(result, str):
                        try:
                            result = json.dumps(redact(json.loads(result), current_secrets), ensure_ascii=False)
                        except ValueError:
                            result = redact(result, current_secrets)
                    else:
                        result = redact(result, current_secrets)
                    entry['status'] = 'succeeded'
                    try:
                        decoded = json.loads(result)
                        if isinstance(decoded, dict) and decoded.get('type') == 'service_result':
                            entry['status'] = decoded['status']
                    except (ValueError, TypeError):
                        pass
                    return result
                except Exception:
                    entry['status'] = 'failed'
                    result = json.dumps({'type': 'tool_execution_error', 'status': 'failed',
                        'message': 'Tool failed. No verified result is available. Do not invent facts.',
                        'may_have_taken_effect': may_write, 'automatic_retry_allowed': False})
                    if may_write and ledger is not None:
                        ledger[key] = result
                    return result
            async def guarded(context, arguments, execute=execute):
                async with execution_lock.get() or asyncio.Lock():
                    return await execute(context, arguments)
            tool.on_invoke_tool = guarded
    return secrets
