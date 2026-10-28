"""Tự sửa sau QA: đọc lỗi QA phát hiện → sửa đúng chỗ → dựng lại → kiểm tra lại (tối đa MAX_ROUNDS vòng).

  Nhãn "[Cảnh N]" lọt vào lời đọc        → bỏ nhãn, đọc lại giọng cảnh đó
  Lời không vừa hình (lặp / phí / chậm)   → Reup: căn lại đoạn hình trước; còn lệch → AI viết lại lời cho vừa số giây, đọc lại
                                             Review: AI viết lại lời cho vừa đoạn hình (editor không kéo giãn hình)
  Hình đứng / màn đen nằm trong 1 cảnh    → coi như lời dài hơn hình của cảnh đó
  Độ dài video lệch lời đọc               → dựng lại
  Âm thanh quá nhỏ / rè                   → chuẩn hoá âm lượng (loudnorm, giữ nguyên hình)
  Thiếu phụ đề                            → xuất lại SRT
Không sửa được gì nữa thì dừng — không dựng lại vô ích.
"""
import os
import shutil

from core.script_writer import strip_scene_label
from .postedit import MAX_STRETCH, rewrite_to_length
from .qa import check_video, media_duration, used_span, video_speed

MAX_ROUNDS = 2
FREEZE_RATIO = 1.1       # lời dài hơn hình quá mức này mới quy hình đứng / màn đen cho cảnh đó


def _clip(s):
    return float(s.get('clip_end') or 0) - float(s.get('clip_start') or 0)


def scene_at(t, scenes, cfg):
    """Thời điểm t (giây, trên video xuất) thuộc cảnh nào. None nếu rơi vào intro/outro.
    Dùng mốc THẬT bước dựng ghi lại (out_start / out_end — đã tính intro, tốc độ, Reup có đoạn lặng giữa các câu);
    thiếu mốc thì ước lượng bằng cộng dồn độ dài lời như cũ."""
    if scenes and all('out_start' in s and 'out_end' in s for s in scenes):
        order = sorted(range(len(scenes)), key=lambda k: float(scenes[k]['out_start']))
        for (n, k) in enumerate(order):
            a = float(scenes[k]['out_start'])
            b = float(scenes[order[n + 1]]['out_start']) if n + 1 < len(order) else float(scenes[k]['out_end']) + 0.5
            if a <= t < b:
                return k
        return None
    t = t * video_speed(cfg) - media_duration(cfg.get('intro_path'))
    acc = 0.0
    for (i, s) in enumerate(scenes):
        acc += float(s.get('tts_duration') or 0)
        if 0 <= t < acc:
            return i
    return None


def plan(qa, scenes, cfg):
    """→ {'scenes': {idx: {'why', 'fit'}}, 'labels': [idx], 'rerender', 'audio', 'srt'}"""
    by = {c['id']: c for c in qa.get('checks', []) if c['status'] != 'ok'}

    def data(cid):
        return by.get(cid, {}).get('data') or {}

    problems = {x['scene']: {'why': x['why'], 'fit': x['fit']} for x in data('sync').get('issues', [])}
    # Lặp lời: viết lại khác đi, giữ độ dài hiện tại (gộp với lỗi độ dài nếu cùng cảnh)
    for x in data('repeat').get('issues', []):
        i = x['scene']
        if i in problems:
            problems[i] = {**problems[i], 'why': problems[i]['why'] + '; ' + x['why'], 'ref': x['with']}
        else:
            problems[i] = {'why': x['why'], 'ref': x['with'], 'text_only': True, 'fit': round(float(scenes[i].get('tts_duration') or _clip(scenes[i])), 1)}
    for (cid, what) in (('freeze', 'hình đứng yên'), ('black', 'màn hình đen')):
        for (start, dur) in data(cid).get('ranges', []):
            i = scene_at(start + dur / 2, scenes, cfg)
            if i is None or i in problems:
                continue
            clip, tts = _clip(scenes[i]), float(scenes[i].get('tts_duration') or 0)
            if clip > 0.1 and tts > clip * FREEZE_RATIO:
                problems[i] = {'why': f'{what} {dur:.1f}s vì lời dài hơn hình', 'fit': round(clip, 1)}
    return {
        'scenes': problems,
        'dups': [x['scene'] for x in data('footage').get('issues', [])],
        'labels': list(data('labels').get('scenes', [])),
        'rerender': 'duration' in by,
        'audio': data('audio').get('issue') in ('quiet', 'clip'),
        'srt': bool(data('subtitle').get('missing')),
    }


def _refit_clips(scenes, problems, video_duration):
    """Reup: nới/cắt đoạn hình cho vừa lời, không lấn sang hình cảnh kế tiếp. → {idx: vấn đề} còn lệch."""
    still = {}
    for (i, pb) in problems.items():
        s = scenes[i]
        start, end = float(s.get('clip_start') or 0), float(s.get('clip_end') or 0)
        tts = float(s.get('tts_duration') or 0)
        if tts > end - start:
            later = [float(x.get('clip_start') or 0) for x in scenes if x is not s and float(x.get('clip_start') or 0) >= end - 0.05]
            s['clip_end'] = round(max(end, min([video_duration or float('inf'), start + tts] + later)), 2)
        elif end - start > tts * MAX_STRETCH:
            s['clip_end'] = round(start + tts * 1.2, 2)
        r = tts / _clip(s) if _clip(s) > 0.1 else 1
        if not (0.7 <= r <= 1.35):
            still[i] = {**pb, 'fit': round(_clip(s), 1)}
    return still


def relocate_footage(scenes, i, video_duration, reup=False):
    """Dời cảnh i sang đoạn hình gốc chưa cảnh nào khác chiếu, đủ dài cho cảnh, gần vị trí cũ nhất. → True nếu dời được."""
    if not video_duration:
        return False
    s = scenes[i]
    a0, a1 = used_span(s, reup)
    need = a1 - a0
    if need <= 0.1:
        return False
    used = sorted(used_span(x, reup) for (k, x) in enumerate(scenes) if k != i and not x.get('excluded'))
    free, t = [], 0.0
    for (u0, u1) in used:
        if u0 - t >= need:
            free.append((t, u0))
        t = max(t, u1)
    if video_duration - t >= need:
        free.append((t, video_duration))
    if not free:
        return False
    # điểm bắt đầu hợp lệ trong mỗi khoảng trống: [f0, f1 - need] — chọn điểm gần chỗ cũ nhất
    best = min((min(max(a0, f0), f1 - need) for (f0, f1) in free), key=lambda x: abs(x - a0))
    clip = float(s.get('clip_end') or 0) - float(s.get('clip_start') or 0)
    s['clip_start'] = round(best, 2)
    s['clip_end'] = round(best + (clip if reup else need), 2)
    return True


def normalize_audio(path, log):
    """Chuẩn hoá âm lượng về -14 LUFS (mức YouTube / TikTok — cùng chuẩn với bước dựng), chép nguyên luồng hình."""
    from core import loudness
    r = loudness.normalize_file(path, 'youtube', log)
    return bool(r) and not r.get('skipped')


def _respeak(job, scenes, i, text, synth, tag):
    sc = dict(scenes[i], voiceover=text)
    if job.config.get('mode', 'review') == 'review' or not sc.get('subtitle'):
        sc['subtitle'] = text
    out = synth(sc, tag)
    if out:
        scenes[i] = out
    return bool(out)


def auto_fix(job, qa, *, video_duration, render, synth, write_srt, log):
    """Vòng tự sửa. render() dựng lại từ job.scenes vào file cũ; synth(scene, tag) → scene có tts_* mới hoặc None;
    write_srt() xuất lại SRT. → qa cuối cùng. Lịch sử sửa lưu ở job.result['qa_fixes']."""
    history = job.result.setdefault('qa_fixes', [])
    reup = job.config.get('mode', 'review') != 'review'
    rewritten = set()            # mỗi cảnh chỉ để AI viết lại 1 lần — tránh sửa qua sửa lại (dài ↔ ngắn)
    for rnd in range(1, MAX_ROUNDS + 1):
        if not any(c['status'] != 'ok' for c in qa['checks']):
            break
        p = plan(qa, job.scenes, job.config)
        if not (p['scenes'] or p['dups'] or p['labels'] or p['rerender'] or p['audio'] or p['srt']):
            log('   [Tự sửa] Lỗi còn lại không tự sửa được (do video gốc / cấu hình) — giữ nguyên.', 'info')
            break
        log(f"[Tự sửa] Vòng {rnd}: {len(set(p['scenes']) | set(p['labels']) | set(p['dups']))} cảnh lỗi" + (', dựng lại' if p['rerender'] else '')
            + (', chuẩn hoá âm lượng' if p['audio'] else '') + (', xuất lại phụ đề' if p['srt'] else ''), 'info')
        actions, touched = [], set()
        scenes = [dict(s) for s in job.scenes]

        # 1. Nhãn lọt vào lời đọc: bỏ nhãn + đọc lại (không cần AI). Cảnh vừa lỗi nhãn vừa lệch hình → để AI viết lại luôn.
        labels = [i for i in p['labels'] if i not in p['scenes']]
        for i in p['labels']:
            scenes[i]['voiceover'] = strip_scene_label(scenes[i].get('voiceover', ''))
        cleaned = sum(_respeak(job, scenes, i, scenes[i]['voiceover'], synth, f'fix{rnd}_lbl{i}') for i in labels)
        if cleaned:
            actions.append(f'bỏ nhãn "[Cảnh…]" + đọc lại {cleaned} cảnh')
            touched |= set(labels)

        # 2. Lặp hình: dời cảnh sang đoạn hình gốc chưa cảnh nào dùng (gần chỗ cũ nhất)
        moved = 0
        for i in p['dups']:
            if relocate_footage(scenes, i, video_duration, reup):
                moved += 1
                touched.add(i)
                log(f"   Cảnh #{i + 1}: chiếu lại hình cảnh khác → dời sang đoạn hình chưa dùng {scenes[i]['clip_start']:.1f}s", 'info')
            else:
                log(f'   Cảnh #{i + 1}: lặp hình nhưng video gốc không còn đoạn nào chưa dùng đủ dài — giữ nguyên', 'info')
        if moved:
            actions.append(f'đổi sang hình chưa dùng {moved} cảnh')

        # 3. Lời không vừa hình / lặp lời
        problems = {i: pb for (i, pb) in p['scenes'].items() if i not in rewritten}
        for (i, pb) in sorted(p['scenes'].items()):
            log(f"   Cảnh #{i + 1}: {pb['why']}" + (' — đã viết lại 1 lần, bỏ qua' if i in rewritten else ''), 'info')
        # Reup: KHÔNG dời mốc câu thoại gốc (bước dựng tự mượn khoảng lặng / tăng tốc giọng — video_editor.reup_fit);
        # cách sửa duy nhất là AI viết lời gọn lại cho vừa khoảng tới câu sau
        if problems:
            new_text = rewrite_to_length(scenes, problems, log)
            spoken = sum(_respeak(job, scenes, i, vo, synth, f'fix{rnd}_{i}') for (i, vo) in new_text.items())
            rewritten |= set(problems)
            if spoken:
                actions.append(f'AI viết lại + đọc lại {spoken} cảnh')
                touched |= set(new_text)
                if not reup:     # Review: đoạn hình của cảnh = đúng phần hình trống AI đã viết cho vừa
                    for i in new_text:
                        if problems[i].get('text_only'):
                            continue     # chỉ lặp lời (giữ độ dài) → không đổi đoạn hình
                        st = float(scenes[i].get('clip_start') or 0)
                        scenes[i]['clip_end'] = round(st + problems[i]['fit'], 2)
            else:
                log('   [Tự sửa] AI chưa viết lại được (chưa đăng nhập ChatGPT/Gemini?)', 'warn')

        changed = scenes != job.scenes
        out = job.result['output_path']
        # sao lưu video + MỌI file phụ đề đi kèm (<tên>.srt / .ass / .vi.srt) — khôi phục thì trả lại đủ bộ
        stem = os.path.splitext(out)[0]
        files = [f for f in (out, stem + '.srt', stem + '.ass', stem + '.vi.srt') if os.path.isfile(f)]
        backup = ([(f, f + '.bak') for f in files], [dict(s) for s in job.scenes], qa)
        for (f, b) in backup[0]:
            shutil.copy2(f, b)                # vòng này làm tệ hơn → khôi phục

        def _restore():
            for (f, b) in backup[0]:
                if os.path.isfile(b):
                    os.replace(b, f)

        def _drop_backup():
            for (_, b) in backup[0]:
                if os.path.isfile(b):
                    os.remove(b)
        before = qa['score']
        try:                                   # lỗi giữa chừng → trả lại đúng bản trước, không để sót .bak (cỡ cả video)
            if changed or p['rerender']:
                job.scenes = scenes
                render()
                actions.append('dựng lại video')
            if p['audio'] and normalize_audio(job.result['output_path'], log):
                actions.append('chuẩn hoá âm lượng')
            if p['srt'] or changed:
                write_srt()
                if p['srt']:
                    actions.append('xuất lại phụ đề')
            if actions:
                qa = check_video(out, job.scenes, job.config, job.result.get('srt_path', ''))
        except BaseException:
            _restore()
            job.scenes = backup[1]
            raise
        if not actions:
            _drop_backup()
            log('   [Tự sửa] Không có thay đổi nào áp dụng được — dừng.', 'info')
            break

        if qa['score'] < before:
            _restore()                         # video + .srt / .ass / .vi.srt của bản trước
            job.scenes, qa = backup[1], backup[2]
            history.append({'round': rnd, 'actions': actions + ['điểm giảm → khôi phục bản trước'], 'before': before, 'after': before,
                            'scenes': [i + 1 for i in sorted(touched)]})
            log(f'   [Tự sửa] Vòng {rnd} làm điểm giảm — đã khôi phục bản trước, dừng.', 'warn')
            break
        _drop_backup()
        history.append({'round': rnd, 'actions': actions, 'before': before, 'after': qa['score'],
                        'scenes': [i + 1 for i in sorted(touched)]})
        log(f"   [Tự sửa] Vòng {rnd}: {', '.join(actions)} → điểm {before} → {qa['score']}", 'ok')
    return qa
