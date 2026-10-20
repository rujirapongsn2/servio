"""Public URL boundary tests and file-backed source lifecycle regressions."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import knowledge_urls as urls
from app import okf_service as service
from app.orm_models import Base, TeamAgent, OKFBundle, OKFConceptIndex


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/file", "https://user:secret@example.com/", "https://example.com:5432/", "http://example.com/\r\nx:1", "https://example.com:bad/"])
def test_reject_invalid_url(url):
    with pytest.raises(urls.URLImportError):
        urls.normalize_url(url)


def test_multiple_unique_urls():
    assert urls.validate_urls(["https://EXAMPLE.com", "https://example.com/two#heading"]) == ["https://example.com/", "https://example.com/two"]
    for value in [[], ["https://example.com"] * 2, [f"https://example.com/{i}" for i in range(21)]]:
        with pytest.raises(urls.URLImportError):
            urls.validate_urls(value)


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.0.0.1"], ["169.254.169.254"], ["::1"], ["fc00::1"], ["fec0::1"], ["64:ff9b::7f00:1"], ["2002:7f00:1::"], ["93.184.216.34", "192.168.1.1"]])
def test_every_dns_address_must_be_public(monkeypatch, addresses):
    monkeypatch.setattr(urls.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, (address, 443)) for address in addresses])
    with pytest.raises(urls.URLImportError, match="public"):
        urls._public_addresses("example.com", 443)


class Response:
    def __init__(self, data="<h1>นโยบายคืนเงิน 45 วัน</h1>".encode(), status=200, headers=None):
        self.data = data
        self.status = status
        self.headers = headers or {"Content-Type": "text/html"}
    def getheader(self, name):
        return self.headers.get(name)
    def read1(self, size):
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


class Connection:
    def __init__(self, response):
        self.response = response
        self.sock = type("Socket", (), {"shutdown": lambda *a: None, "close": lambda *a: None, "settimeout": lambda *a: None})()
    def connect(self):
        pass
    def request(self, *args, **kwargs):
        self.request_args = args, kwargs
    def getresponse(self):
        return self.response
    def close(self):
        pass


def network(monkeypatch, responses):
    calls = []
    monkeypatch.setattr(urls.socket, "getaddrinfo", lambda host, *a, **k: [(None,None,None,None,("127.0.0.1" if host == "internal.example" else "93.184.216.34",443))])
    def connection(scheme, host, port, address, timeout):
        calls.append((scheme,host,port,address))
        return Connection(responses.pop(0))
    monkeypatch.setattr(urls, "_open_connection", connection)
    return calls


def test_download_uses_validated_address_and_html_extraction(monkeypatch):
    calls = network(monkeypatch, [Response()])
    sources, warnings = service._collect_url_sources(["https://example.com/policy"])
    assert sources[0].source_url == "https://example.com/policy"
    assert sources[0].text == "นโยบายคืนเงิน 45 วัน"
    assert calls == [("https","example.com",443,"93.184.216.34")]


def test_private_redirect_rejected_before_connection(monkeypatch):
    calls = network(monkeypatch, [Response(status=302, headers={"Location":"http://internal.example/secret"})])
    with pytest.raises(urls.URLImportError, match="public"):
        urls.download_url("https://example.com/")
    assert len(calls) == 1


@pytest.mark.parametrize("response", [Response(b"short",headers={"Content-Type":"text/plain","Content-Length":"20"}), Response(b"",headers={"Content-Type":"text/plain"}), Response(b"binary",headers={"Content-Type":"image/png"}), Response(b"x",headers={"Content-Type":"text/plain","Content-Length":str(urls.MAX_BYTES+1)}), Response(status=503)])
def test_bad_download_does_not_import(monkeypatch, response):
    network(monkeypatch,[response])
    with pytest.raises(urls.URLImportError):
        urls.download_url("https://example.com/")


def test_pinned_https_preserves_hostname():
    from unittest.mock import Mock
    with patch.object(urls.socket,"create_connection",return_value=Mock()) as connect:
        connection = urls._open_connection("https","example.com",443,"93.184.216.34",5)
        assert connection.host == "example.com"
        connection._create_connection(("example.com",443),5)
        assert connect.call_args.args[0] == ("93.184.216.34",443)
        assert 0 < connect.call_args.args[1] <= 5
        assert connect.call_args.args[2] is None
        assert connection._context.check_hostname
        assert connection._context.verify_mode == urls.ssl.CERT_REQUIRED


@pytest.fixture
def store(tmp_path,monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine,expire_on_commit=False)
    @contextmanager
    def get_db():
        with sessions() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
    monkeypatch.setattr(service,"get_db",get_db)
    with get_db() as db:
        db.add(TeamAgent(id=1,name="Owner",slug="default"))
    yield service.OKFService(tmp_path / "knowledge"), get_db
    engine.dispose()


def import_two(store,monkeypatch):
    network(monkeypatch,[Response(b"<p>Original policy</p>"),Response(b"<p>Original policy</p>")])
    api,_ = store
    bundle = api.import_knowledge_files([],"URL sources",1,"team",None,urls=["https://example.com/one","https://example.com/two"])
    concepts = api.list_concepts(bundle['id'],1)
    assert len(concepts) == 2
    return bundle, concepts


def test_distinct_identical_sources_and_preview(store,monkeypatch):
    bundle, concepts = import_two(store,monkeypatch)
    assert {item['resource'] for item in concepts} == {"https://example.com/one","https://example.com/two"}
    assert len({item['concept_id'] for item in concepts}) == 2
    for concept in concepts:
        detail = store[0].get_concept(bundle['id'],concept['concept_id'],1)
        assert detail['frontmatter']['source_url'] == concept['resource']
        assert detail['frontmatter']['fetched_at']


def test_edit_then_refresh_replaces_only_selected_source(store,monkeypatch):
    api,_ = store
    bundle, concepts = import_two(store,monkeypatch)
    selected = concepts[0]
    edited = api.update_concept(bundle['id'],selected['concept_id'],1,"Edited title",None,["custom"],"Manual override",selected['updated_at'])
    assert edited['frontmatter']['source_url'] == selected['resource']
    network(monkeypatch,[Response(b"<p>Updated remote policy 60 days</p>")])
    refreshed = api.reindex_source(bundle['id'],selected['concept_id'],1,url="https://example.com/changed",expected_updated_at=edited['updated_at'])
    assert refreshed['concept_id'] == selected['concept_id']
    assert refreshed['title'] == "Edited title"
    assert refreshed['tags'] == ["custom"]
    assert refreshed['resource'] == "https://example.com/changed"
    assert "60 days" in refreshed['body'] and "Manual override" not in refreshed['body']
    other = api.get_concept(bundle['id'],concepts[1]['concept_id'],1)
    assert "Original policy" in other['body']
    assert len(api.list_concepts(bundle['id'],1)) == 2


def test_failed_fetch_preserves_existing_bundle(store,monkeypatch):
    api,_ = store
    bundle, concepts = import_two(store,monkeypatch)
    network(monkeypatch,[Response(b"<p>New first</p>"),Response(status=404)])
    with pytest.raises(service.OKFValidationError):
        api.reindex_bundle(bundle['id'],1)
    for concept in concepts:
        assert "Original policy" in api.get_concept(bundle['id'],concept['concept_id'],1)['body']


def test_reindex_all_replaces_without_accumulation(store,monkeypatch):
    api,_ = store
    bundle, concepts = import_two(store,monkeypatch)
    for _ in range(2):
        network(monkeypatch,[Response(b"<p>Fresh 90 days</p>"),Response(b"<p>Fresh 120 days</p>")])
        api.reindex_bundle(bundle['id'],1)
        updated = api.list_concepts(bundle['id'],1)
        assert {item['concept_id'] for item in updated} == {item['concept_id'] for item in concepts}
        assert all('Original policy' not in api.get_concept(bundle['id'],item['concept_id'],1)['body'] for item in updated)


def test_stale_edit_rejected_before_fetch(store,monkeypatch):
    api,_ = store
    bundle, concepts = import_two(store,monkeypatch)
    selected = concepts[0]
    api.update_concept(bundle['id'],selected['concept_id'],1,None,None,None,'Concurrent edit')
    monkeypatch.setattr(urls,'download_url',lambda *a,**k:pytest.fail('Stale request must not fetch'))
    with pytest.raises(service.OKFValidationError, match='changed'):
        api.reindex_source(bundle['id'],selected['concept_id'],1,expected_updated_at=selected['updated_at'])


def test_edit_during_fetch_does_not_overwrite(store,monkeypatch):
    api,_ = store
    bundle, concepts = import_two(store,monkeypatch)
    def download(url,**kwargs):
        api.update_concept(bundle['id'],concepts[0]['concept_id'],1,None,None,None,'Concurrent edit')
        return urls.DownloadedSource(url,url,'.txt',b'Remote content')
    monkeypatch.setattr(urls,'download_url',download)
    with pytest.raises(service.OKFValidationError, match='changed'):
        api.reindex_source(bundle['id'],concepts[0]['concept_id'],1)
    assert 'Concurrent edit' in api.get_concept(bundle['id'],concepts[0]['concept_id'],1)['body']


def test_commit_failure_restores_source_files(store,monkeypatch):
    api,get_db = store
    bundle,concepts = import_two(store,monkeypatch)
    original = api.get_concept(bundle['id'],concepts[0]['concept_id'],1)
    network(monkeypatch,[Response(b'<p>Replacement must roll back</p>')])
    from sqlalchemy.orm import Session
    original_commit = Session.commit
    with monkeypatch.context() as patcher:
        patcher.setattr(Session,'commit',lambda db: (_ for _ in ()).throw(RuntimeError('simulated commit failure')) if db.info.get('fail_commit') else original_commit(db))
        replace = api._replace_index
        def mark(db,*args):
            replace(db,*args)
            db.info['fail_commit'] = True
        patcher.setattr(api,'_replace_index',mark)
        with pytest.raises(RuntimeError,match='commit failure'):
            api.reindex_source(bundle['id'],concepts[0]['concept_id'],1)
    after = api.get_concept(bundle['id'],concepts[0]['concept_id'],1)
    assert after['markdown'] == original['markdown']
    assert after['body'] == original['body']


def test_dns_deadline_and_bounded_workers(monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    blocker = threading.Event()
    calls = []
    def resolve(*args, **kwargs):
        calls.append(args)
        blocker.wait(5)
        return [(None,None,None,None,("93.184.216.34",443))]
    monkeypatch.setattr(urls.socket,"getaddrinfo",resolve)
    try:
        with ThreadPoolExecutor(max_workers=4) as requests:
            futures = [requests.submit(urls._public_addresses,"example.com",443,deadline=time.monotonic()+0.1) for _ in range(4)]
            for future in futures:
                with pytest.raises(urls.URLImportError,match="timed out"):
                    future.result(timeout=1)
        assert len(calls) == 4
        with pytest.raises(urls.URLImportError,match="timed out"):
            urls._public_addresses("example.com",443,deadline=time.monotonic()+0.05)
        assert len(calls) == 4
    finally:
        blocker.set()


def test_remote_word_xml_is_bounded_before_expansion(monkeypatch):
    import io
    import zipfile
    from app.local_documents import MAX_XML_BYTES
    archive = io.BytesIO()
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr('word/document.xml',b'<document>' + b'x' * MAX_XML_BYTES + b'</document>')
    assert len(archive.getvalue()) < urls.MAX_BYTES
    network(monkeypatch,[Response(archive.getvalue(),headers={'Content-Type':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'})])
    with pytest.raises(service.OKFValidationError,match='16MB'):
        service._collect_url_sources(['https://example.com/document.docx'])
