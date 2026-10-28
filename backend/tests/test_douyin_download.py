"""Tải Douyin: cookie người dùng nạp (3 dạng), thứ tự thử nguồn, nguồn miễn phí tạm nghỉ / hồi lại, bấm dừng.
Không gọi mạng — giả lập nguồn tải + yt-dlp."""
import json
import time

import pytest

from core import downloader as D
from core import site_cookies as SC

URL = 'https://www.douyin.com/video/7680657798694243611'
FUTURE = int(time.time()) + 30 * 86400


@pytest.fixture
def cookie_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, 'COOKIE_DIR', str(tmp_path))
    return tmp_path


# ── cookie: đọc 3 dạng, lọc đúng tên miền, kiểm tra phiên ──

def test_parse_netscape_keeps_only_douyin(cookie_dir):
    txt = ('# Netscape HTTP Cookie File\n'
           f'.douyin.com\tTRUE\t/\tTRUE\t{FUTURE}\ts_v_web_id\tverify_abc\n'
           f'#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t{FUTURE}\tttwid\t1|xyz\n'
           f'.google.com\tTRUE\t/\tTRUE\t{FUTURE}\tSID\tsecret\n')
    rows = SC.parse(txt, 'douyin')
    assert {r[4] for r in rows} == {'s_v_web_id', 'ttwid'}      # cookie Google bị bỏ, HttpOnly vẫn đọc


def test_parse_json_and_header(cookie_dir):
    js = json.dumps([{'name': 'ttwid', 'value': 'a', 'domain': '.douyin.com', 'expirationDate': FUTURE},
                     {'name': 'x', 'value': 'b', 'domain': 'example.com'}])
    assert [r[4] for r in SC.parse(js, 'douyin')] == ['ttwid']
    assert {r[4] for r in SC.parse('s_v_web_id=v1; ttwid=t2', 'douyin')} == {'s_v_web_id', 'ttwid'}


def test_save_rejects_wrong_content(cookie_dir):
    with pytest.raises(ValueError):
        SC.save('douyin', '')
    with pytest.raises(ValueError):                              # không có cookie Douyin nào
        SC.save('douyin', f'.google.com\tTRUE\t/\tTRUE\t{FUTURE}\tSID\tx\tx')
    with pytest.raises(ValueError):                              # có cookie Douyin nhưng thiếu phần phiên
        SC.save('douyin', 'foo=1; bar=2')
    assert not SC.status('douyin')['has']


def test_save_status_args_delete(cookie_dir):
    st = SC.save('douyin', 's_v_web_id=v1; ttwid=t2')
    assert st['has'] and st['count'] == 2
    f = SC.path('douyin')
    assert open(f, encoding='utf-8').read().startswith('# Netscape HTTP Cookie File')
    assert SC.ytdlp_args('douyin') == ['--cookies', f]
    assert SC.ytdlp_args('tiktok') == []                          # nền tảng khác không dính cookie Douyin
    assert not SC.delete('douyin')['has'] and SC.ytdlp_args('douyin') == []


def test_status_reports_expiry(cookie_dir):
    past = int(time.time()) - 86400
    SC.save('douyin', f'.douyin.com\tTRUE\t/\tTRUE\t{past}\tttwid\tt')
    assert SC.status('douyin')['expires_in_days'] <= 0


# ── luồng tải Douyin ──

class Fake:
    """Giả lập: dtk (nguồn miễn phí), yt-dlp (theo extra args), download_direct."""
    def __init__(self, monkeypatch, dtk=None, ytdlp=None):
        self.calls = []
        self.dtk, self.ytdlp = dtk, ytdlp or {}
        monkeypatch.setattr(D, 'dtk_resolve', self._dtk)
        monkeypatch.setattr(D, '_ytdlp_download', self._yt)
        monkeypatch.setattr(D, 'download_direct', lambda u, *a, **k: (self.calls.append(('direct', u)), 'E:/x/direct.mp4')[1])
        monkeypatch.setattr(D, '_BROWSER_BAD', {})

    def _dtk(self, url, **kw):
        self.calls.append(('dtk',))
        if isinstance(self.dtk, Exception):
            raise self.dtk
        return {'platform_label': 'Douyin', 'height': 1080, 'title': 't', 'cover': 'c', 'video': 'https://v.cdn/x.mp4'}

    def _yt(self, url, out, q, extra, *a):
        key = extra[1] if extra else 'plain'
        key = 'cookie' if key.endswith('.txt') else key
        self.calls.append(('yt', key))
        r = self.ytdlp.get(key, (None, 'ERROR: [Douyin] 1: Fresh cookies (not necessarily logged in) are needed'))
        return r


def test_no_cookie_uses_free_source(cookie_dir, monkeypatch):
    f = Fake(monkeypatch)
    assert D.download(URL, 'E:/x', log_fn=lambda *_: None) == 'E:/x/direct.mp4'
    assert f.calls == [('dtk',), ('direct', 'https://v.cdn/x.mp4')]


def test_user_cookie_tried_first_and_wins(cookie_dir, monkeypatch):
    SC.save('douyin', 's_v_web_id=v; ttwid=t')
    f = Fake(monkeypatch, ytdlp={'cookie': ('E:/x/ok.mp4', '')})
    assert D.download(URL, 'E:/x', log_fn=lambda *_: None) == 'E:/x/ok.mp4'
    assert f.calls == [('yt', 'cookie')]                         # không đụng tới nguồn miễn phí


def test_bad_cookie_falls_back_to_free_source(cookie_dir, monkeypatch):
    SC.save('douyin', 's_v_web_id=v; ttwid=t')
    f = Fake(monkeypatch)
    assert D.download(URL, 'E:/x', log_fn=lambda *_: None) == 'E:/x/direct.mp4'
    assert f.calls[:2] == [('yt', 'cookie'), ('dtk',)]


def test_free_source_busy_message_and_browser_skip(cookie_dir, monkeypatch):
    f = Fake(monkeypatch, dtk=D.DtkBusy('nguồn Douyin đang tạm nghỉ', 4),
             ytdlp={b: (None, 'ERROR: Could not copy Chrome cookie database') for b in ('chrome', 'edge', 'firefox')})
    with pytest.raises(RuntimeError) as e:
        D.download(URL, 'E:/x', log_fn=lambda *_: None)
    assert 'khoảng 4 phút' in str(e.value) and 'Cookie Douyin' in str(e.value)
    assert ('yt', 'chrome') in f.calls
    # lần sau: trình duyệt đã biết là đọc không được → bỏ qua, không tốn thời gian
    f.calls.clear()
    with pytest.raises(RuntimeError):
        D.download(URL, 'E:/x', log_fn=lambda *_: None)
    assert not any(c[0] == 'yt' and c[1] in ('chrome', 'edge', 'firefox') for c in f.calls)


def test_cookie_rejected_then_ok_is_tracked(cookie_dir, monkeypatch):
    SC.save('douyin', 's_v_web_id=v; ttwid=t')
    Fake(monkeypatch)                                             # cookie bị từ chối, nguồn miễn phí cứu
    D.download(URL, 'E:/x', log_fn=lambda *_: None)
    assert SC.status('douyin')['rejected'] is True
    Fake(monkeypatch, ytdlp={'cookie': ('E:/x/ok.mp4', '')})
    D.download(URL, 'E:/x', log_fn=lambda *_: None)
    assert SC.status('douyin')['rejected'] is False
    # nạp lại cookie mới → bỏ trạng thái "bị từ chối" cũ
    Fake(monkeypatch)
    D.download(URL, 'E:/x', log_fn=lambda *_: None)
    time.sleep(1.1)
    SC.save('douyin', 's_v_web_id=v2; ttwid=t2')
    assert SC.status('douyin')['rejected'] is False


def test_unrelated_error_does_not_blame_cookie(cookie_dir, monkeypatch):
    SC.save('douyin', 's_v_web_id=v; ttwid=t')
    Fake(monkeypatch, ytdlp={'cookie': (None, 'ERROR: This video has been removed')})
    D.download(URL, 'E:/x', log_fn=lambda *_: None)
    assert SC.status('douyin')['rejected'] is False


def test_expired_cookie_message(cookie_dir, monkeypatch):
    SC.save('douyin', 's_v_web_id=v; ttwid=t')
    Fake(monkeypatch, dtk=D.DtkBusy('bận', 0))
    with pytest.raises(RuntimeError) as e:
        D.download(URL, 'E:/x', log_fn=lambda *_: None)
    assert 'hết hạn' in str(e.value)


def test_cancel_inside_free_source_stops(cookie_dir, monkeypatch):
    f = Fake(monkeypatch, dtk=RuntimeError('Đã huỷ.'))
    with pytest.raises(RuntimeError, match='Đã huỷ'):
        D.download(URL, 'E:/x', log_fn=lambda *_: None)
    assert f.calls == [('dtk',)]                                  # không chạy tiếp cách dự phòng


# ── dtk_resolve: gửi việc → hỏi kết quả, tự chờ khi nguồn bận ──

class Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


RESULT = {'kind': 'video', 'platform': 'douyin', 'title': 'Phim', 'author': {'nickname': 'A'}, 'duration_ms': 5000,
          'media': {'video': {'url': 'https://v.cdn/a.mp4', 'width': 1080, 'height': 1920}, 'covers': [{'url': 'https://c/1.jpg'}]}}


class Sess:
    def __init__(self, states):
        self.states, self.posts = list(states), 0

    def post(self, url, **kw):
        self.posts += 1
        return Resp(202, {'success': True, 'data': {'task_id': f't{self.posts}', 'state': 'queued'}})

    def get(self, url, **kw):
        st = self.states[min(self.posts, len(self.states)) - 1]
        return Resp(200, {'success': True, 'data': st})


@pytest.fixture
def fast(monkeypatch):
    from core import cancel
    slept = []
    monkeypatch.setattr(cancel, 'sleep', lambda s, step=0.25: (slept.append(s), False)[1])
    return slept


def test_dtk_task_success(monkeypatch, fast):
    s = Sess([{'state': 'succeeded', 'result': RESULT}])
    monkeypatch.setattr(D, '_dtk_session', lambda fresh=False: s)
    v = D.dtk_resolve(URL)
    assert v['video'] == 'https://v.cdn/a.mp4' and v['height'] == 1920 and v['cover'] == 'https://c/1.jpg' and v['duration'] == 5


def test_dtk_retries_after_risk_control(monkeypatch, fast):
    busy = {'state': 'failed', 'error': {'code': 'UPSTREAM_RISK_CONTROL', 'retryable': True, 'retry_after': 60}}
    s = Sess([busy, {'state': 'succeeded', 'result': RESULT}])
    monkeypatch.setattr(D, '_dtk_session', lambda fresh=False: s)
    logs = []
    v = D.dtk_resolve(URL, log_fn=logs.append)
    assert v['title'] == 'Phim' and s.posts == 2
    assert 60 in fast and any('tự thử lại sau 60 giây' in m for m in logs)


def test_dtk_gives_up_fast_when_wait_too_long(monkeypatch, fast):
    s = Sess([{'state': 'failed', 'error': {'code': 'ENDPOINT_CIRCUIT_OPEN', 'retryable': True, 'retry_after': 600}}])
    monkeypatch.setattr(D, '_dtk_session', lambda fresh=False: s)
    t0 = time.time()
    with pytest.raises(D.DtkBusy) as e:
        D.dtk_resolve(URL, budget=240)
    assert e.value.minutes == 10 and s.posts == 1 and 600 not in fast and time.time() - t0 < 5


def test_dtk_non_retryable_error(monkeypatch, fast):
    s = Sess([{'state': 'failed', 'error': {'code': 'NOT_FOUND', 'message': 'post deleted', 'retryable': False}}])
    monkeypatch.setattr(D, '_dtk_session', lambda fresh=False: s)
    with pytest.raises(RuntimeError, match='NOT_FOUND') as e:
        D.dtk_resolve(URL)
    assert not isinstance(e.value, D.DtkBusy) and s.posts == 1


def test_dtk_image_post_rejected(monkeypatch, fast):
    s = Sess([{'state': 'succeeded', 'result': {**RESULT, 'kind': 'images'}}])
    monkeypatch.setattr(D, '_dtk_session', lambda fresh=False: s)
    with pytest.raises(RuntimeError, match='bài ảnh'):
        D.dtk_resolve(URL)


# ── xem trước link: lỗi "nguồn bận" là lỗi mềm — vẫn cho bấm Tải ──

def test_probe_douyin_busy_is_soft(cookie_dir, monkeypatch):
    def busy(url, **kw):
        raise D.DtkBusy('bận', 3)
    monkeypatch.setattr(D, 'dtk_resolve', busy)
    ran = []
    monkeypatch.setattr(D, '_ytdlp', lambda args, **kw: (ran.append(args), (1, '', 'x'))[1])
    r = D.probe(URL)
    assert r.get('soft') is True and 'Vẫn bấm' in r['error']
    assert ran == []                                              # không cookie → không chạy yt-dlp thừa


def test_probe_other_platform_error_not_soft(cookie_dir, monkeypatch):
    monkeypatch.setattr(D, '_ytdlp', lambda args, **kw: (1, '', 'ERROR: Video unavailable. This video is private'))
    r = D.probe('https://www.youtube.com/watch?v=xxxxxxxxxxx')
    assert 'soft' not in r and 'riêng tư' in r['error']
