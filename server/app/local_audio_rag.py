from __future__ import annotations
import base64
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from pathlib import Path
import httpx
import jwt
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import Response
from sqlalchemy import text
from app.db_config import engine, get_db
from app.orm_models import OKFBundle, OKFConceptIndex, TeamAgent
from app.knowledge_audio import enabled, ExtractedAudio, MAX_BYTES, process_audio

router = APIRouter()
_schema_ready = False
_schema_lock = threading.Lock()
_lock = threading.Lock()


class LocalAudioEmbeddingClient:
    def __init__(self):
        base = os.getenv('AUDIO_EMBEDDING_BASE_URL', 'http://host.docker.internal:8093/v1').rstrip('/')
        if not base.startswith(('http://', 'https://')):
            raise ValueError('AUDIO_EMBEDDING_BASE_URL must use HTTP(S)')
        self.url = base + '/embeddings'
        self.model = os.getenv('AUDIO_EMBEDDING_MODEL', 'servio-embeddinggemma2-audio')
        self.query_prefix = os.getenv('AUDIO_QUERY_PREFIX', 'task: search result | query: ')
        self.revision = os.getenv('AUDIO_EMBEDDING_REVISION', '')
        if not self.revision:
            raise ValueError('Set AUDIO_EMBEDDING_REVISION to the exact weights and projection revision')
        self.timeout = min(300, max(1, float(os.getenv('AUDIO_EMBEDDING_TIMEOUT_SECONDS', '180'))))

    def space(self, fingerprint):
        return hashlib.sha256(json.dumps([self.model, self.query_prefix, self.revision, fingerprint, 'native-pcm16-mono16k-v1']).encode()).hexdigest()

    def _request(self, value):
        response = httpx.post(self.url, json={'model': self.model, 'input': [value]}, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()['data']
        if len(data) != 1 or data[0].get('index') != 0:
            raise ValueError('Invalid audio embedding response')
        vector = data[0]['embedding']
        if len(vector) != 768 or not all(type(x) in {int, float} and math.isfinite(x) for x in vector) or not any(vector):
            raise ValueError('Expected finite nonzero 768-dimensional audio vector')
        return vector

    def audio(self, wav):
        if not wav or len(wav) > 2 * 1024 * 1024 or wav[:4] != b'RIFF' or wav[8:12] != b'WAVE':
            raise ValueError('Expected bounded normalized WAV segment')
        return self._request({'content': [{'type': 'input_audio', 'input_audio': {'data': base64.b64encode(wav).decode(), 'format': 'wav'}}]})

    def query(self, query):
        if not query.strip() or len(query) > 3000:
            raise ValueError('Audio query must contain 1 to 3000 characters')
        return self._request(self.query_prefix + query.strip())


def _literal(vector):
    return '[' + ','.join(format(x, '.9g') for x in vector) + ']'


def ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with engine.begin() as conn:
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS okf_audio_vectors (
                bundle_id INTEGER NOT NULL REFERENCES okf_bundles(id) ON DELETE CASCADE,
                concept_id VARCHAR(1000) NOT NULL, segment_id VARCHAR(10) NOT NULL,
                asset_id VARCHAR(64) NOT NULL, source_hash VARCHAR(64) NOT NULL,
                fingerprint VARCHAR(64) NOT NULL, space VARCHAR(64) NOT NULL,
                start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, transcript TEXT NOT NULL,
                embedding vector(768) NOT NULL, PRIMARY KEY(bundle_id,concept_id,segment_id))'''))
        _schema_ready = True


def _asset(root, frontmatter):
    metadata = ExtractedAudio.model_validate(frontmatter['audio'])
    relative = frontmatter['audio_asset_path']
    if not isinstance(relative, str):
        raise ValueError('Invalid audio asset path')
    candidate = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Unsafe audio asset path')
    current = root
    for component in Path(relative).parts:
        current = current / component
        if current.is_symlink():
            raise ValueError('Unsafe audio asset symlink')
    path = candidate.resolve()
    if not path.is_relative_to((root / 'assets').resolve()) or not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Unsafe audio asset path')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != metadata.asset_id:
        raise ValueError('Audio source changed; re-upload original')
    return metadata, data


def build_records(root, concepts):
    from app.okf_service import _ensure_within, _parse_frontmatter
    client = LocalAudioEmbeddingClient()
    records = []
    for concept in concepts:
        path = root / concept.file_path
        _ensure_within(root, path)
        markdown = path.read_text(encoding='utf-8')
        if hashlib.sha256(markdown.encode()).hexdigest() != concept.content_hash:
            raise ValueError('Knowledge source changed; reindex source first')
        fm, _ = _parse_frontmatter(markdown, concept.file_path)
        if 'audio' not in fm:
            continue
        metadata, data = _asset(root, fm)
        normalized, wavs = process_audio(data, normalize=True)
        if [(s.start_ms,s.end_ms) for s in normalized.segments] != [(s.start_ms,s.end_ms) for s in metadata.segments]:
            raise ValueError('Segmentation changed; refresh audio source first')
        if not isinstance(wavs, list) or len(wavs) != len(metadata.segments):
            raise ValueError('Invalid normalized audio segment count')
        for segment, encoded in zip(metadata.segments, wavs):
            if not isinstance(encoded, str) or len(encoded) > 3 * 1024 * 1024:
                raise ValueError('Audio segment exceeds limit')
            wav = base64.b64decode(encoded, validate=True)
            vector = client.audio(wav)
            records.append({'concept': concept.concept_id, 'source': concept.content_hash, 'asset': metadata.asset_id,
                'segment': segment.segment_id, 'start': segment.start_ms, 'end': segment.end_ms,
                'transcript': segment.transcript, 'fingerprint': metadata.fingerprint,
                'space': client.space(metadata.fingerprint), 'vector': _literal(vector)})
    return records


def replace_records(conn, bundle_id, records):
    conn.execute(text('DELETE FROM okf_audio_vectors WHERE bundle_id=:bundle'), {'bundle': bundle_id})
    for record in records:
        conn.execute(text('''INSERT INTO okf_audio_vectors(bundle_id,concept_id,segment_id,asset_id,source_hash,fingerprint,space,start_ms,end_ms,transcript,embedding)
            VALUES(:bundle,:concept,:segment,:asset,:source,:fingerprint,:space,:start,:end,:transcript,CAST(:vector AS vector))'''), {'bundle': bundle_id, **record})


def index_bundle(bundle_id):
    if not enabled():
        return {'status': 'disabled', 'segments': 0}
    from app.okf_service import parse_okf_directory
    with _lock:
        ensure_schema()
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle:
                raise KeyError('Knowledge not found')
            root = Path(bundle.storage_path)
            concepts, _ = parse_okf_directory(root)
            hashes = {c.concept_id: c.content_hash for c in concepts}
            indexed = {c.concept_id: c.content_hash for c in db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).all()}
            if hashes != indexed:
                raise ValueError('Knowledge source changed; reindex source first')
        records = build_records(root, concepts)
        with engine.begin() as conn:
            if conn.execute(text('SELECT id FROM okf_bundles WHERE id=:bundle FOR UPDATE'), {'bundle': bundle_id}).scalar() is None:
                raise ValueError('Knowledge deleted during indexing')
            current = dict(conn.execute(text('SELECT concept_id,content_hash FROM okf_concept_index WHERE bundle_id=:bundle'), {'bundle':bundle_id}).all())
            actual, _ = parse_okf_directory(root)
            if current != hashes or {c.concept_id:c.content_hash for c in actual} != hashes:
                raise ValueError('Knowledge changed during indexing; retry')
            replace_records(conn, bundle_id, records)
        return {'status':'ready','segments':len(records)}


def try_index_bundle(bundle_id):
    try:
        return index_bundle(bundle_id)
    except Exception:
        logging.getLogger(__name__).exception('Audio indexing unavailable for bundle %s', bundle_id)
        return {'status':'failed','segments':0}


def _grant(bundle_id, concept_id, asset_id, source_hash, team_id):
    from app.auth import SECRET_KEY, ALGORITHM
    return jwt.encode({'purpose':'knowledge-audio','bundle':bundle_id,'concept':concept_id,'asset':asset_id,'source':source_hash,'team':team_id,'exp':int(time.time())+900}, SECRET_KEY, algorithm=ALGORITHM)


def _resolve_asset(claims):
    from app.okf_service import _bundle_available_to_team, _ensure_within, _parse_frontmatter
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=claims['team']).first()
        bundle = db.query(OKFBundle).filter_by(id=claims['bundle']).first()
        if not team or team.status != 'active' or not bundle or not _bundle_available_to_team(db,bundle,team.id):
            raise ValueError('Audio unavailable')
        concept = db.query(OKFConceptIndex).filter_by(bundle_id=bundle.id,concept_id=claims['concept']).first()
        if not concept or concept.content_hash != claims['source']:
            raise ValueError('Audio source changed')
        root = Path(bundle.storage_path)
        path = root / concept.file_path
        _ensure_within(root,path)
        markdown = path.read_text(encoding='utf-8')
        if hashlib.sha256(markdown.encode()).hexdigest() != claims['source']:
            raise ValueError('Audio source changed')
        fm,_ = _parse_frontmatter(markdown,concept.file_path)
        metadata,data = _asset(root,fm)
        if metadata.asset_id != claims['asset']:
            raise ValueError('Audio source changed')
        return data,metadata,concept.title,concept.resource or concept.title


def byte_range(value, size):
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()):
        raise ValueError('Invalid range')
    lo, hi = match.groups()
    if not lo:
        length = int(hi)
        if length <= 0:
            raise ValueError('Invalid range')
        return max(0,size-length),size-1
    start = int(lo)
    end = min(size-1,int(hi)) if hi else size-1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable range')
    return start,end


@router.get('/api/knowledge-audio/{asset_id}')
def original_audio(asset_id: str, token: str, range: str | None = Header(default=None)):
    from app.auth import SECRET_KEY, ALGORITHM
    try:
        if not enabled() or len(token)>4096:
            raise ValueError('Audio unavailable')
        claims = jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM],options={'require':['exp','purpose','team','bundle','concept','asset','source']})
        if claims['purpose']!='knowledge-audio' or claims['asset']!=asset_id:
            raise ValueError('Invalid audio grant')
        data,metadata,_,_ = _resolve_asset(claims)
    except (jwt.PyJWTError,ValueError,KeyError,OSError,TypeError):
        raise HTTPException(404,'Audio unavailable or link expired') from None
    headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Accept-Ranges':'bytes'}
    if range is not None:
        try:
            lo,hi=byte_range(range,len(data))
        except ValueError:
            return Response(status_code=416,headers={**headers,'Content-Range':f'bytes */{len(data)}'})
        return Response(data[lo:hi+1],status_code=206,media_type=metadata.mime,headers={**headers,'Content-Range':f'bytes {lo}-{hi}/{len(data)}'})
    return Response(data,media_type=metadata.mime,headers=headers)


def hydrate_audio(references, team_id, bundle_id, *, links=True):
    """Caller must bind unsigned references to a real authorized tool call."""
    if not enabled() or team_id is None or not isinstance(references,list) or not 1<=len(references)<=5:
        return []
    result=[]
    for ref in references:
        if not isinstance(ref,dict) or ref.get('bundle_id')!=bundle_id:
            return []
        claims={'bundle':bundle_id,'concept':ref['concept_id'],'asset':ref['asset_id'],'source':ref['source_hash'],'team':team_id}
        data,metadata,title,label=_resolve_asset(claims)
        segment=next((s for s in metadata.segments if s.segment_id==ref['segment_id']),None)
        if segment is None:
            return []
        card={'asset_id':metadata.asset_id,'title':title,'source_label':label,'segment_id':segment.segment_id,'start_ms':segment.start_ms,'end_ms':segment.end_ms,'transcript':segment.transcript,'transcript_status':metadata.transcript_status}
        if links:
            card['audio_url']=f'/api/knowledge-audio/{metadata.asset_id}?token='+_grant(bundle_id,ref['concept_id'],metadata.asset_id,ref['source_hash'],team_id)
        else:
            card.update(bundle_id=bundle_id,concept_id=ref['concept_id'],source_hash=ref['source_hash'])
        result.append(card)
    return result


def fuse_segments(native, transcript, *, limit=3):
    """Fuse by canonical segment, then collapse overlapping or repeated windows."""
    merged={}
    for rows,weight in ((native,1.0),(transcript,2.0)):
        for rank,row in enumerate(rows,1):
            key=(row['concept_id'],row['segment_id'])
            if key not in merged:
                merged[key]={**row,'fusion_score':0.0}
            merged[key]['fusion_score']+=weight/(60+rank)
    selected=[]
    for row in sorted(merged.values(),key=lambda item:item['fusion_score'],reverse=True):
        duplicate=False
        for previous in selected:
            if previous['concept_id']!=row['concept_id']:
                continue
            overlap=max(0,min(previous['end_ms'],row['end_ms'])-max(previous['start_ms'],row['start_ms']))
            shortest=min(previous['end_ms']-previous['start_ms'],row['end_ms']-row['start_ms'])
            if overlap>=shortest/2 or (row.get('transcript') and row.get('transcript')==previous.get('transcript')):
                duplicate=True
                break
        if not duplicate:
            selected.append(row)
        if len(selected)>=limit:
            break
    return selected


def transcript_ranking(root, concepts, query, text_concepts):
    from app.okf_service import _ensure_within,_parse_frontmatter
    terms=list(dict.fromkeys([query.strip().lower()]+re.findall(r'[\w\u0E00-\u0E7F]{2,}',query.lower())))[:20]
    hybrid={row['concept_id']:rank for rank,row in enumerate(text_concepts,1)}
    rows=[]
    for concept in concepts:
        path=root/concept.file_path
        _ensure_within(root,path)
        markdown=path.read_text(encoding='utf-8')
        if hashlib.sha256(markdown.encode()).hexdigest()!=concept.content_hash:
            continue
        fm,_=_parse_frontmatter(markdown,concept.file_path)
        if 'audio' not in fm:
            continue
        metadata=ExtractedAudio.model_validate(fm['audio'])
        for segment in metadata.segments:
            if not segment.transcript.strip():
                continue
            lower=segment.transcript.lower()
            matches=sum((10 if i==0 else 1) for i,term in enumerate(terms) if term in lower)
            if not matches and concept.concept_id not in hybrid:
                continue
            rows.append({'concept_id':concept.concept_id,'segment_id':segment.segment_id,'asset_id':metadata.asset_id,
                'source_hash':concept.content_hash,'start_ms':segment.start_ms,'end_ms':segment.end_ms,
                'transcript':segment.transcript,'lexical_score':matches,'hybrid_rank':hybrid.get(concept.concept_id,999)})
    return sorted(rows,key=lambda row:(-row['lexical_score'],row['hybrid_rank'],row['start_ms']))[:30]


def query_bundle(bundle_id,query,team_agent_id,limit=5,*,audio_links=True,text_concepts=None):
    if not enabled() or team_agent_id is None or not query.strip():
        return []
    from app.okf_service import _bundle_available_to_team
    with get_db() as db:
        team=db.query(TeamAgent).filter_by(id=team_agent_id).first()
        bundle=db.query(OKFBundle).filter_by(id=bundle_id).first()
        if not team or team.status!='active' or not bundle or not _bundle_available_to_team(db,bundle,team.id):
            return []
        root=Path(bundle.storage_path)
        concepts=db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).all()
        transcript=transcript_ranking(root,concepts,query,text_concepts or [])
    native=[]
    try:
        ensure_schema()
        client=LocalAudioEmbeddingClient()
        with engine.connect() as conn:
            fingerprints=conn.execute(text('SELECT DISTINCT fingerprint,space FROM okf_audio_vectors WHERE bundle_id=:bundle'),{'bundle':bundle_id}).all()
        spaces=[space for fingerprint,space in fingerprints if client.space(fingerprint)==space]
        if spaces:
            vector=client.query(query)
            with engine.connect() as conn:
                rows=conn.execute(text('''SELECT v.concept_id,v.asset_id,v.segment_id,v.source_hash,v.space,v.start_ms,v.end_ms,v.transcript,1-(v.embedding <=> CAST(:vector AS vector)) AS score
                    FROM okf_audio_vectors v JOIN okf_concept_index k ON k.bundle_id=v.bundle_id AND k.concept_id=v.concept_id AND k.content_hash=v.source_hash
                    WHERE v.bundle_id=:bundle ORDER BY v.embedding <=> CAST(:vector AS vector) LIMIT 100'''),{'bundle':bundle_id,'vector':_literal(vector)}).mappings().all()
            current=[dict(row) for row in rows if row['space'] in spaces]
            if current:
                threshold=max(float(os.getenv('AUDIO_MIN_SCORE','0.15')),current[0]['score']-float(os.getenv('AUDIO_SCORE_MARGIN','0.025')))
                native=[row for row in current if row['score']>=threshold][:10]
    except Exception:
        logging.getLogger(__name__).exception('Native audio retrieval unavailable; preserving transcript matches')
    selected=fuse_segments(native,transcript,limit=max(1,min(limit,int(os.getenv('AUDIO_MAX_RESULTS','3')),5)))
    result=[]
    for row in selected:
        ref={key:row[key] for key in ('concept_id','asset_id','segment_id','source_hash')}
        ref['bundle_id']=bundle_id
        try:
            result.extend(hydrate_audio([ref],team_agent_id,bundle_id,links=audio_links))
        except (ValueError,KeyError,OSError,TypeError):
            continue
    return result
