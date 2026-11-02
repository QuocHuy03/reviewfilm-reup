"""MCP: /mcp chặn khi thiếu / sai token, cho qua khi đúng token; đủ bộ lệnh; /api/mcp trả cấu hình dán sẵn."""
import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.features.mcp.server import ensure_token, mcp

EXPECTED = {'list_languages', 'list_voices', 'test_voice', 'download_videos', 'create_video_job', 'list_jobs', 'get_job',
            'wait_for_job', 'get_outputs', 'cancel_job', 'retry_job', 'get_script', 'update_script', 'approve_step',
            'export_subtitles', 'app_status'}
HDR = {'accept': 'application/json, text/event-stream', 'content-type': 'application/json'}
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '1'}}}


def test_tools_registered():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert EXPECTED <= names


def test_token_guard_and_info():
    with TestClient(app, base_url='http://127.0.0.1:47651') as c:
        assert c.post('/mcp/', json=INIT, headers=HDR).status_code == 401
        assert c.post('/mcp/', json=INIT, headers={**HDR, 'authorization': 'Bearer wrong'}).status_code == 401
        r = c.post('/mcp/', json=INIT, headers={**HDR, 'authorization': f'Bearer {ensure_token()}'})
        assert r.status_code == 200 and r.json()['result']['serverInfo']['name'] == 'ReviewFilm Studio'
        info = c.get('/api/mcp').json()
        assert info['token'] == ensure_token() and info['url'].endswith('/mcp/')
        assert info['claude_desktop']['mcpServers']['reviewfilm']['args'][-1] == '--mcp-stdio'
        assert 'Authorization' in info['cursor']['mcpServers']['reviewfilm']['headers']


def test_cancel_before_wait_does_not_hang(monkeypatch):
    """Bấm Dừng ngay trước bước chờ duyệt → huỷ luôn, không treo ở 'waiting' (lỗi cũ: clear() nuốt tín hiệu Dừng)."""
    import pytest
    from app.features.jobs import manager as m
    job = m.Job('vietsub', {'inp': 'x'}, 't')
    monkeypatch.setattr(job, 'save', lambda *a, **k: None)
    job.cancel()
    with pytest.raises(m.JobCancelled):
        job.wait_for('script', 'Chờ')
    assert job.status != 'waiting'


def test_job_brief_reads_log_messages():
    from app.features.mcp.server import _job_brief
    j = {'id': 'x', 'status': 'running', 'logs': [{'t': 1, 'msg': '[1] Đọc phụ đề', 'tag': 'info'}, {'t': 2, 'msg': 'xong', 'tag': 'ok'}],
         'result': {'output_path': r'E:\a\b.mp4', 'hardsub_source': True}}
    b = _job_brief(j)
    assert b['recent_log'] == ['[1] Đọc phụ đề', 'xong'] and b['files'] == {'output_path': r'E:\a\b.mp4'}
