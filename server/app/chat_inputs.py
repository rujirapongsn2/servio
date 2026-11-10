"""Validated customer inputs, shared by Private Chat and Web Chat."""
import base64
import io
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.agent_execution import MAX_MESSAGE_CHARS

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
MAX_ENCODED_BYTES = 4 * ((MAX_ATTACHMENT_BYTES + 2) // 3)


class ChatAttachment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['image', 'audio', 'file', 'video']
    name: str = Field(min_length=1, max_length=255)
    mime: str = Field(min_length=1, max_length=100)
    base64: str = Field(min_length=4, max_length=MAX_ENCODED_BYTES)

    def data(self):
        try:
            result = base64.b64decode(self.base64, validate=True)
        except ValueError:
            raise ValueError('Invalid attachment encoding') from None
        limit = 10 * 1024 * 1024 if self.kind == 'image' else MAX_ATTACHMENT_BYTES
        if not 0 < len(result) <= limit:
            raise ValueError('Attachment exceeds the supported size')
        return result


class ChatInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(default='', max_length=MAX_MESSAGE_CHARS)
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=8)
    image_search: bool = False
    speak: bool = False
    request_id: str | None = Field(default=None, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')

    @model_validator(mode='after')
    def nonempty(self):
        if not self.message.strip() and not self.attachments:
            raise ValueError('Enter a message or attach media')
        if self.image_search and (len(self.attachments) != 1 or self.attachments[0].kind != 'image'):
            raise ValueError('Image search requires exactly one image')
        if sum(len(item.base64) for item in self.attachments) > MAX_ENCODED_BYTES:
            raise ValueError('Attachments exceed the shared request budget')
        return self


async def prepare_input(request):
    """Audio uses the same STT model/settings as the Channel voice pipeline."""
    from app.chat_media import transcribe
    message = request.message
    remaining = []
    for attachment in request.attachments:
        if attachment.kind == 'audio':
            transcript = await transcribe(attachment)
            message = '\n'.join(part for part in (message, transcript) if part)
        else:
            remaining.append(attachment)
    return text_and_images(message, remaining)


def display_text(content):
    if isinstance(content, str):
        return content
    return '\n'.join(part.get('text', '[image]') for part in content if isinstance(part, dict))


def text_and_images(message, attachments):
    parts = [{'type': 'input_text', 'text': message}] if message else []
    total = 0
    for attachment in attachments:
        data = attachment.data()
        total += len(data)
        if total > MAX_ATTACHMENT_BYTES:
            raise ValueError('Attachments exceed the total request size')
        if attachment.kind == 'image':
            from app.local_image_rag import validated_image
            _, mime = validated_image(data)
            if mime != attachment.mime:
                raise ValueError('Image MIME does not match its contents')
            parts.append({'type': 'input_image', 'image_url': f'data:{mime};base64,{attachment.base64}', 'detail': 'auto'})
        elif attachment.kind == 'file':
            if attachment.mime == 'application/pdf':
                if not data.startswith(b'%PDF-'):
                    raise ValueError('Invalid PDF')
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(data))
                if reader.is_encrypted or len(reader.pages) > 200:
                    raise ValueError('Use an unencrypted PDF with at most 200 pages')
                text = '\n'.join(page.extract_text() or '' for page in reader.pages)
                if not text.strip():
                    raise ValueError('This PDF has no text layer; attach page images for visual analysis')
            elif attachment.mime in ('text/plain', 'text/csv', 'application/json', 'text/markdown'):
                text = data.decode('utf-8-sig')
            else:
                raise ValueError('Supported files: TXT, CSV, JSON, Markdown and text-layer PDF')
            if len(text) > 500_000:
                raise ValueError('Extracted document exceeds the shared input budget')
            parts.append({'type': 'input_text', 'text': 'Untrusted attached file data:\n' + json.dumps({'filename': attachment.name, 'text': text}, ensure_ascii=False)})
        else:
            raise ValueError('Audio/video require the shared media adapter')
    return message if not attachments else parts
