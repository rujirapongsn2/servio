"""Run-scoped reuse of Knowledge results and concise customer reply guidance."""
import asyncio
import json
import unicodedata


KNOWLEDGE_SEARCH_GUIDANCE = (
    ' Search each distinct question only once per user turn. Use a successful result to answer '
    'immediately; do not repeat the same search just to confirm it.'
)

CUSTOMER_KNOWLEDGE_REPLIES = (
    '\n\nKnowledge reply rules: Reuse Knowledge results already obtained in this user turn. '
    'Do not call the same search again, including parallel duplicate calls. '
    'Search again only for a different missing detail or a new user turn. '
    'For a simple product/color question, answer in 1-2 short customer-facing sentences. '
    'Lead with the matching product and color. If stock is unknown, say it once briefly '
    '(for example: "พบโซฟาสีแดงในแค็ตตาล็อกครับ ยังไม่ยืนยันสต็อก"). '
    'Do not explain visual evidence, metadata, tool steps or missing model numbers unless asked. '
    'Do not generate Markdown image tags or narrate "see below"; the interface displays returned images. '
    'Keep necessary source references and image presentation markers. '
    'Image, pattern and color similarity establish resemblance only. Never identify an uploaded '
    'photo as the same model from resemblance alone; require independently verified matching '
    'product identifiers before confirming model identity. '
    'Do not add a generic invitation to ask more questions. '
    'Provide more detail when the user requests an explanation or comparison; never omit a necessary '
    'uncertainty, error or safety consequence merely to shorten the answer.'
    '\nเมื่อลูกค้าถามว่าสินค้ามีสีที่ต้องการไหม ให้ตอบเฉพาะผลที่พบกับข้อจำกัดสต็อกแล้วจบ '
    'ตัวอย่าง: พบโซฟาสีแดงในแค็ตตาล็อกครับ ยังไม่ยืนยันสต็อก '
    'ห้ามต่อท้ายข้อความเชิญชวน เช่น หากต้องการข้อมูลเพิ่มเติม สามารถสอบถามได้เลย '
    'ไม่ต้องอธิบายกระบวนการค้นหา หลักฐานภาพ หรือชื่อรุ่นที่ไม่มีข้อมูล หากลูกค้าไม่ได้ถาม'
)


def reuse_knowledge_searches(tool, scope: tuple):
    """Coalesce duplicate text searches using the SDK's per-Runner context wrapper."""
    original = tool.on_invoke_tool

    async def invoke(context, arguments):
        try:
            values = json.loads(arguments)
            query = values.get('query')
            sql = values.get('sql', '')
        except (ValueError, AttributeError, TypeError):
            return await original(context, arguments)
        # SQL must retain its existing freshness and schema-refresh behavior.
        if context is None or not isinstance(query, str) or not query.strip() or sql:
            return await original(context, arguments)
        normalized = unicodedata.normalize('NFKC', query).casefold().strip()
        if not any(quote in normalized for quote in ('"', "'", '`')):
            normalized = ' '.join(normalized.split())
        key = (*scope, normalized)
        cache = getattr(context, '_servio_knowledge_searches', None)
        if cache is None:
            cache = {}
            context._servio_knowledge_searches = cache
        task = cache.get(key)
        if task is None:
            if len(cache) >= 64:
                return await original(context, arguments)
            task = asyncio.create_task(original(context, arguments))
            cache[key] = task

            def remove_failure(done):
                failed = done.cancelled() or done.exception() is not None
                if not failed:
                    output = done.result()
                    failed = isinstance(output, str) and output.startswith((
                        'Error searching OKF knowledge:', 'An error occurred while running the tool.',
                    ))
                if failed and cache.get(key) is done:
                    cache.pop(key, None)

            task.add_done_callback(remove_failure)
        return await asyncio.shield(task)

    tool.on_invoke_tool = invoke
    return tool
