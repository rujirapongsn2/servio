import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from app.knowledge_image_presentations import KnowledgeImage, hydrate_knowledge_images


class KnowledgeAudio(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    asset_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    title: str = Field(min_length=1,max_length=1000)
    source_label: str = Field(min_length=1,max_length=2000)
    segment_id: str = Field(pattern=r'^s[0-9]{4}$')
    start_ms: int = Field(ge=0,le=600000)
    end_ms: int = Field(gt=0,le=600000)
    transcript: str = Field(max_length=20000)
    transcript_status: Literal['ready','empty']
    audio_url: str = Field(max_length=4096)

    @field_validator('audio_url')
    @classmethod
    def validate_url(cls,value,info):
        import re
        if not re.fullmatch('/api/knowledge-audio/'+re.escape(info.data.get('asset_id',''))+r'\?token=[A-Za-z0-9_.-]+',value):
            raise ValueError('Signed local audio URL required')
        return value


class KnowledgeMedia(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    type: Literal['knowledge_media'] = 'knowledge_media'
    version: Literal[1] = 1
    response: str = Field(max_length=64000)
    images: list[KnowledgeImage] = Field(default_factory=list,max_length=5)
    audio: list[KnowledgeAudio] = Field(default_factory=list,max_length=5)


def hydrate_knowledge_media(value,team_agent_id,bundle_id):
    if team_agent_id is None:
        return None
    try:
        if isinstance(value,str):
            if len(value)>256000:
                return None
            value=json.loads(value)
        if not isinstance(value,dict) or value.get('type')!='knowledge_media_refs' or type(value.get('version')) is not int or value.get('version')!=1:
            return None
        if set(value)-{'type','version','response','audio','images'} or not isinstance(value.get('response'),str):
            return None
        from app.local_audio_rag import hydrate_audio
        audio=hydrate_audio(value.get('audio',[]),team_agent_id,bundle_id)
        if not audio:
            return None
        images=[]
        if value.get('images'):
            presentation=hydrate_knowledge_images({'type':'knowledge_image_refs','version':1,'response':value['response'],'images':value['images']},team_agent_id,bundle_id)
            if presentation:
                images=presentation.images
        return KnowledgeMedia(response=value['response'],audio=audio,images=images)
    except (ValueError,KeyError,TypeError,OSError,ValidationError):
        return None
