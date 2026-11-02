"""/api/mcp: thông tin kết nối MCP cho trang Cài đặt (địa chỉ, token, cấu hình dán sẵn cho từng client) + chặn /mcp khi
thiếu token."""
import json
import os
import secrets
import sys

from fastapi import APIRouter

from .server import ensure_token, read_info, _write_info

router = APIRouter(prefix='/api/mcp', tags=['mcp'])

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class McpTokenGuard:
    """ASGI bọc app MCP: cần 'Authorization: Bearer <token>' (hoặc ?token=…). Chặn trang web lạ trong trình duyệt gọi
    vào cổng localhost (trình duyệt không tự gắn header này)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            token = ensure_token()
            headers = {k.decode('latin-1').lower(): v.decode('latin-1') for (k, v) in scope.get('headers') or []}
            auth = headers.get('authorization', '')
            q = (scope.get('query_string') or b'').decode('latin-1')
            given = auth[7:] if auth.startswith('Bearer ') else next((p[6:] for p in q.split('&') if p.startswith('token=')), '')
            ok = bool(given) and secrets.compare_digest(given.encode(), token.encode())
            if not ok:
                body = json.dumps({'error': 'unauthorized', 'detail': 'Thiếu hoặc sai token MCP — lấy ở ReviewFilm Studio → Cài đặt → Kết nối AI (MCP).'},
                                  ensure_ascii=False).encode()
                await send({'type': 'http.response.start', 'status': 401,
                            'headers': [(b'content-type', b'application/json; charset=utf-8'), (b'www-authenticate', b'Bearer')]})
                await send({'type': 'http.response.body', 'body': body})
                return
        await self.app(scope, receive, send)


def _configs(port, token):
    url = f'http://127.0.0.1:{port}/mcp/'      # có '/' cuối: khỏi bị chuyển hướng 307 (vài client không theo)
    py = sys.executable
    main_py = os.path.join(BACKEND_DIR, 'main.py')
    stdio = {'command': py, 'args': [main_py, '--mcp-stdio']}
    if os.environ.get('RF_DATA_DIR'):          # bản cài: dữ liệu (mcp.json) ở %APPDATA% — cầu stdio phải đọc đúng chỗ
        stdio['env'] = {'RF_DATA_DIR': os.environ['RF_DATA_DIR']}
    return {
        'url': url,
        'token': token,
        # Claude Desktop: chỉ chạy lệnh (stdio) với server trên máy → dùng cầu stdio của chính app
        'claude_desktop': {'mcpServers': {'reviewfilm': stdio}},
        # Cursor / VS Code / Windsurf: hỗ trợ HTTP + header
        'cursor': {'mcpServers': {'reviewfilm': {'url': url, 'headers': {'Authorization': f'Bearer {token}'}}}},
        'claude_code': f'claude mcp add --transport http reviewfilm {url} --header "Authorization: Bearer {token}"',
        'stdio': stdio,
    }


@router.get('')
def mcp_info():
    info = read_info()
    port = os.environ.get('RF_PORT') or info.get('port')
    return {'enabled': True, 'port': port, **_configs(port, ensure_token())}


@router.post('/rotate-token')
def rotate_token():
    """Đổi token (lỡ lộ) — client đã cấu hình phải dán lại."""
    info = read_info()
    info['token'] = secrets.token_urlsafe(24)
    _write_info(info)
    return mcp_info()
