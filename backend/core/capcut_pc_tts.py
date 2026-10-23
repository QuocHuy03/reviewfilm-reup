"""Giọng CapCut qua API bản PC (editor-api-sg.capcutapi.com) — dùng cho các giọng mà API web từ chối
(err 40402004, vd nhóm multi_*_uranus_bigtts). Không cần cookie/đăng nhập: mã thiết bị tự sinh.

Luồng: POST /lv/v1/common_task/new → id+token → POST /lv/v1/common_task/query (poll) → tải mp3.
Ký request: header `sign` = md5 + `x-ss-stub` = md5(body) + chữ ký RSA PKCS#1 v1.5 trên payload TTS.
Tham khảo: E:/titktikapp/backend/capcut/capcut_tts.py
"""
import base64
import hashlib
import json
import secrets
import time
import uuid
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import requests

BASE_URL = 'https://editor-api-sg.capcutapi.com'

_RSA_PEM_B64 = (
    'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmTd34Lw4b7IuldSXh/zY'
    'CMla+ITdGG5TeWz6ad+OySd4r+IrY45AoqrYUxhQ2dl+7z+i7r/5vEa8rr39BYfB'
    '8AGMQLmZA8HmgpWBsqrn/V6daUALkKnkLb70Fn32CJigIuGXAYqxUdGuI340aC+0'
    'v5Es3puJsHyzf01/AelE4Cdc6bZhQrASJLBh8R3BQToYClmDVSDUQk28o8sl/guA'
    'Z4n303Vj+6Siv1HayPCdV6kpVVnMBAG4+umUbwGmn132N3fgpzLarFF3XyWmS1zh'
    'D/J07iM/rP8GDO9IskHNHd2phrO0G6KzrcFAnTBHjVv+hCBEfzN/no3FNA9AuC36'
    'mwIDAQAB'
)


def _new_device():
    did = str(secrets.randbelow(9 * 10 ** 19) + 10 ** 19)  # 20 chữ số
    return {
        'aid': '359289', 'app_name': 'CapCut', 'appvr': '8.7.0', 'version_name': '8.7.0', 'version_code': '8.7.0',
        'channel': 'capcutpc_google', 'device_platform': 'mac', 'device_type': 'MacBookPro17,4',
        'device_brand': 'MacBookPro17,4', 'os_version': '15.7.4', 'device_id': did, 'iid': did,
        'region': 'VN', 'loc': 'VN', 'lan': 'vi-VN', 'pf': '3', 'tdid': did,
    }


_DEV = _new_device()   # cố định trong phiên


def _cjson(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def _md5(s):
    return hashlib.md5(s.encode('utf-8') if isinstance(s, str) else s).hexdigest()


def _rsa_numbers():
    """Đọc modulus/exponent từ khoá công khai DER (SubjectPublicKeyInfo) — không cần thư viện crypto."""
    der = base64.b64decode(_RSA_PEM_B64)

    def rd(d, p, tag):
        assert d[p] == tag
        p += 1
        n = d[p]
        p += 1
        if n >= 0x80:
            k = n & 0x7F
            n, p = int.from_bytes(d[p:p + k], 'big'), p + k
        return d[p:p + n], p + n

    outer, _ = rd(der, 0, 0x30)
    _, p = rd(outer, 0, 0x30)
    bits, _ = rd(outer, p, 0x03)
    seq, _ = rd(bits[1:], 0, 0x30)
    mod, p2 = rd(seq, 0, 0x02)
    exp, _ = rd(seq, p2, 0x02)
    return int.from_bytes(mod, 'big'), int.from_bytes(exp, 'big')


_MOD, _EXP = _rsa_numbers()


def _rsa_sign(message):
    klen = (_MOD.bit_length() + 7) // 8
    msg = message.encode('utf-8')
    ps_len = klen - len(msg) - 3
    ps = bytearray()
    while len(ps) < ps_len:
        ps.extend(b for b in secrets.token_bytes(ps_len - len(ps)) if b)
    block = b'\x00\x02' + bytes(ps[:ps_len]) + b'\x00' + msg
    ct = pow(int.from_bytes(block, 'big'), _EXP, _MOD).to_bytes(klen, 'big')
    return base64.b64encode(ct).decode('ascii')


def _post(path, body_obj, babi=None, region=True):
    dev = _DEV
    body = _cjson(body_obj)
    q = {k: dev[k] for k in ('app_name', 'device_type', 'os_version', 'channel', 'version_name', 'device_brand',
                             'device_id', 'iid', 'version_code', 'device_platform', 'aid')}
    if region:
        q['region'] = dev['region']
    if babi is not None:
        q['babi_param'] = _cjson(babi)
    url = BASE_URL + path + '?' + urlencode(q)
    now = str(int(time.time()))
    h = {
        'content-type': 'application/json', 'appvr': dev['appvr'], 'ch': dev['channel'], 'device-time': now,
        'lan': dev['lan'], 'loc': dev['loc'], 'pf': dev['pf'], 'sign-ver': '1', 'tdid': dev['tdid'],
        'x-ss-stub': _md5(body), 'x-ss-dp': dev['aid'], 'x-khronos': now,
        'x-tt-trace-id': f'00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01',
        'user-agent': 'Cronet/TTNetVersion:1d7cc3b1 2025-07-16 QuicVersion:52c2b40d 2025-04-03',
        'accept-encoding': 'gzip, deflate', 'store-country-code': 'vn', 'store-country-code-src': 'did',
        'app-sdk-version': dev['appvr'], 'appid': dev['aid'],
        'sign': _md5(f"9e2c|{path[-7:]}|3|{dev['appvr']}|{now}|{dev['tdid']}|11ac"),
    }
    r = requests.post(url, headers=h, data=body.encode('utf-8'), timeout=60, allow_redirects=False)
    return r.json()


def synthesize(text, voice_type, resource_id, speed=1.0, timeout=120):
    """→ bytes mp3. Lỗi thì ném RuntimeError (kèm lý do ngắn)."""
    babi = {'feature_entrance': 'editor', 'feature_entrance_detail': 'editor-feature-text_to_speech',
            'feature_key': 'text_to_speech', 'scenario': 'video_editor'}
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">\n'
        f'    <voice name="{voice_type}" mock_tone_info="" platform="sami" resource_id="{resource_id}" emotion="" '
        'emotion_scale="0" style="" role="" moyin_emotion="" is_clone_tone="false" need_subtitle_timestamp="false">\n'
        f'        <prosody rate="{round(speed, 2)}">{escape(text)}</prosody>\n'
        '    </voice>\n</speak>'
    )
    extra = _cjson({'benefit_info': {}})
    payload = {'audio_format': 'mp3', 'babi_param': _cjson(babi), 'credit_disable': False, 'extra_info': extra,
               'need_merge_voice': False, 'need_subtitle_timestamp': False, 'scene': 'text_to_speech', 'ssml': ssml}
    payload['sign'] = _rsa_sign(f"appid:{_DEV['aid']}&did:{_DEV['device_id']}&creditDisable:false"
                                f"&ssml:{_md5(ssml)}&extraInfo:{extra}")
    body = {'bind_id': str(uuid.uuid4()), 'can_queue': True, 'enter_from': 'text_to_speech',
            'tasks': [{'context': str(uuid.uuid4()), 'payload': _cjson(payload),
                       'req_key': 'sami_text_to_speech', 'task_version': 'v3'}]}
    res = _post('/lv/v1/common_task/new', body, babi)
    if str(res.get('ret')) not in ('0', 'None', ''):
        raise RuntimeError(f"CapCut PC từ chối: {res.get('errmsg') or 'lỗi không rõ'} (ret={res.get('ret')})")
    t = ((res.get('data') or {}).get('tasks') or [{}])[0]
    if not t.get('id'):
        raise RuntimeError('CapCut PC không trả mã tác vụ')
    bind = t.get('bind_id') or (res.get('data') or {}).get('bind_id') or ''
    q_body = {'tasks': [{'bind_id': bind, 'id': t['id'], 'req_key': 'sami_text_to_speech',
                         'task_version': 'v3', 'token': t.get('token', '')}]}
    deadline = time.time() + timeout
    while time.time() < deadline:
        q = _post('/lv/v1/common_task/query', q_body, region=False)
        qt = ((q.get('data') or {}).get('tasks') or [{}])[0]
        status = str(qt.get('status', '')).lower()
        if status in ('success', 'succeed', 'succeeded', 'done'):
            p = qt.get('payload')
            p = json.loads(p) if isinstance(p, str) else (p or {})
            for item in p.get('audio_subtitles') or []:
                url = item.get('speech_url') or item.get('audio_url') or item.get('url')
                if url:
                    a = requests.get(url, timeout=60)
                    if a.status_code == 200 and len(a.content) > 1000:
                        return a.content
                    raise RuntimeError(f'Tải audio CapCut PC lỗi (HTTP {a.status_code})')
            raise RuntimeError('CapCut PC không trả link audio')
        if status == 'failed':
            raise RuntimeError('CapCut PC báo tác vụ thất bại')
        time.sleep(1)
    raise RuntimeError('CapCut PC quá thời gian chờ')
