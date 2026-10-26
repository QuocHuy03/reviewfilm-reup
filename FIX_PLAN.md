# Kế hoạch sửa: vùng che lệch, giọng lệch timeline, âm lượng, phụ đề, kịch bản

## ✅ Trạng thái (cập nhật 2026-10-26)

Bộ test `backend/tests`: **18/18 PASS** (16 test gốc + 2 test mới cho mô hình Reup). Đã chạy thật 1 job Reup trọn vẹn (QA 92/100, đủ 13/13 cảnh, mỗi đoạn hình chỉ chiếu 1 lần).

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| A1–A4 vùng che | ✅ | test pass |
| B1 Reup không tua nhanh / chậm tuỳ tiện | ✅ | `video_editor.reup_fit` dùng chung cho dựng, SRT, QA, xem trước |
| B2 không gộp block 12s | ✅ | ≤6s, ≤100 ký tự, khoảng lặng <0.35s |
| B3 hook nhét vào thoại | ✅ | bỏ hook (hàm dịch dùng chung cả Dịch phụ đề) |
| B4 SRT lệch | ✅ | ghi SRT SAU khi dựng theo độ dài clip thật + intro + tốc độ; `.vi.srt` = file đó |
| B5 cắt lặng TTS | ✅ | `polish_tts` cho mọi engine |
| B6 Whisper | ✅ | Reup bật mốc theo từ; câu gợi ý đúng ngôn ngữ nguồn |
| B7 ngân sách độ dài | ✅ | `toi_da N tu` mỗi câu + AI rút gọn câu phải chậm hình (Reup) |
| B8 tự hậu kỳ trên Reup | ✅ | không `fix_durations`, không cho AI bỏ câu; câu người dùng bỏ giữ tiếng gốc nhỏ |
| B9 phụ đề theo WordBoundary | ⏳ chưa làm | tuỳ chọn (chỉ Edge có mốc từ); hiện chia theo ký tự — giống hệt giữa xem trước & xuất |
| B10 hình khớp lời kể (Review) | ✅ | Vision chỉ xem phần hình sẽ chiếu (`_shown_span`) |
| B11 lặp hình (Review) | ✅ | `review_cap`: hình không lấn sang cảnh sau, lời dư → chậm nhẹ / giữ khung |
| B12 chia đều lời khi thiếu nhãn | ✅ | không chia đều; dự phòng bắt buộc nhãn; mô tả giả không bao giờ thành lời |
| B13 lỗi nhỏ kịch bản | ✅ (trừ TTS_WPM) | mốc "12s"/"1:23"; thoại mẫu đều cả phim; khung hình từ đầu phim; AI hậu kỳ thấy mô tả hình |
| C1 amix | ✅ | test pass |
| C2 cân âm lượng TTS | ✅ | ≈ -17…-18 LUFS mọi engine |
| D1, D2 | ✅ | test pass |
| D3 sửa lời mà giọng cũ | ✅ | `tts_text` + lỗi đỏ ở Hậu kỳ + tự đọc lại khi xác nhận |
| D4 regen gắn nhầm cảnh | ✅ | ghép theo mã cố định |
| D5 VieNeu dùng file cũ | ✅ | xoá file đích trước khi tạo (Edge, CapCut, VieNeu) |
| D6 phân vai | ✅ | so khớp bỏ khoảng trắng; thiếu / ghép lỗi → đọc lại cả câu giọng người kể |
| E1 dấu % | ✅ | test pass |
| E2 quá số dòng | ✅ | |
| E3 xem trước ≠ xuất | ✅ (trừ kiểu chữ) | cùng nguồn chữ, cùng thuật toán chia đoạn (đã đối chiếu 5/5), chia theo ký tự, bỏ line-clamp |
| E4 cỡ chữ ASS | ✅ | chỉ "Ghép phụ đề" (Dịch phụ đề giữ cỡ hiện tại) |
| E5 lỗi nhỏ | ✅ | gte/lt, fmt_ts, ≤ số dòng, log font |
| F1–F4 QA / tự sửa | ✅ | mốc thật từ bước dựng; hoàn tác đủ bộ file; QA đếm cảnh bị bỏ; QA Reup theo mô hình mới; fps thật |
| G1 đọc số | ✅ | 7/7 + phụ đề giữ chữ số |
| G2 engine | ✅ | CapCut nhận tốc độ (khi chỉ định); VieNeu không treo; Edge ghi lý do lỗi; lỗi đọc file báo đúng |
| H1–H7 | ✅ | |

---

Mục lục: A. Vùng che · B. Timeline giọng đọc (B1–B9 Reup/chung, B10–B13 Review) · C. Âm lượng · D. Giọng gắn nhầm cảnh · E. Phụ đề · F. QA/tự sửa · G. Đọc số & engine TTS · H. Khác

Review ngày 2026-10-24, trên commit `6c79ce7`. Mọi lỗi dưới đây đã **đọc code + tái hiện bằng ffmpeg thật**, trừ chỗ ghi rõ "chưa tái hiện".

## 0. Cách kiểm (làm trước khi sửa)

Có sẵn test tái hiện ở `backend/tests/` (chưa commit). Hiện tại chúng **FAIL — đúng như mong đợi**:

```
cd backend
python -m pytest tests -q --tb=line
```

| Test | Hiện tại | Lỗi nó bắt |
|---|---|---|
| `test_cover_boxes.py::test_box_covers_text_same_aspect` | FAIL (1408 px chữ lọt ra) | A1, A4 |
| `test_cover_boxes.py::test_box_covers_logo_when_mirrored` | FAIL | A2 |
| `test_cover_boxes.py::test_box_covers_text_letterboxed_vertical_source` | FAIL | A1 |
| `test_cover_boxes.py::test_box_follows_per_scene_zoom[1.2]` | FAIL | A3 |
| `test_cover_boxes.py::test_unboxed_text_stays_sharp` | FAIL | A1 (đối chứng) |
| `test_reup_timing.py::test_reup_short_voice_does_not_fast_forward_video` | FAIL (video gốc 6s → xuất ra 2.6s) | B1 |
| `test_reup_timing.py::test_reup_srt_matches_rendered_clip_lengths` | FAIL (câu 2 lệch 0.43s) | B4 |
| `test_audio_mix.py::test_bgm_does_not_halve_voice` | FAIL (giọng −6 dB khi có nhạc nền) | C1 |
| `test_audio_mix.py::test_timeline_sfx_do_not_duck_voice` | FAIL (giọng −14 dB khi có 4 SFX) | C1 |
| `test_audio_mix.py::test_reup_gap_keeps_original_audio_level` | FAIL (tiếng gốc −12 dB ở đoạn không thoại) | C1 |
| `test_voice_index.py::test_tts_keeps_caller_scene_index` | FAIL (cảnh 3, 7 thành 0, 1) | D1 |
| `test_voice_index.py::test_multi_voice_output_not_duplicated` | FAIL (3 cảnh thành 6) | D2 |
| `test_subtitle_burn.py::test_special_chars_in_subtitle_render[…50%…]` | FAIL (cảnh bị bỏ) | E1 |

Ngoài các test trên, mọi phát hiện còn lại trong file đều đã được kiểm bằng cách đọc code. Mục nào chưa chắc chắn thì có ghi "(chưa chắc)".

Sửa xong thì mọi test phải PASS. Test tạo video tổng hợp có "chữ cứng" (sọc trắng 2px) ở vị trí biết trước rồi đếm điểm ảnh còn trắng sắc sau khi dựng. Không cần video thật.
Gợi ý: thêm `.claude/verify.json` với `{"commands": ["cd backend && python -m pytest tests -q"], "timeout": 300}` để hook tự chạy bộ test.

---

## A. Che sub cũ / che tên (logo) bị lệch chỗ

**Gốc chung:** người dùng kéo vùng che trên khung xem trước (`CoverBoxEditor.tsx`, `Monitor.tsx`). Khung đó chỉ **co hình gốc + thêm viền đen** (object-contain). Còn backend (`_process_one_scene`, `backend/core/video_editor.py`) lại làm mờ **sau khi** đã biến đổi hình thêm nhiều bước (`fc = [0:v]{vf}[vbase]` rồi blur trên `vbase`, dòng 708). Vì thế toạ độ % của vùng che không còn trỏ đúng vào chữ gốc.

### A1. Zoom 3% chống bản quyền chạy TRƯỚC bước làm mờ — lỗi chính, ảnh hưởng mọi video
- `video_editor.py:603` `crop=iw*0.97:ih*0.97,scale=…` nằm trong `vf`, tức chạy trước blur.
- Chữ ở y=84% trên preview thật ra rơi vào y≈85.1%, mép dưới 94% thành 95.4%. Mép chữ bị hở 1–2% khung (≈15–20px ở 1080p), bên trái/phải cũng hở như vậy. Đây đúng là hiện tượng "che nhầm chỗ".

### A2. Lật gương chạy TRƯỚC bước làm mờ
- `video_editor.py:559` `hflip` nằm trong `vf`. Logo ở góc trái bị lật sang phải, nhưng vùng che vẫn ở bên trái.
- Thêm nữa, `mirror_video=bool(mirror_video) and i % 2 == 0` (dòng 340) chỉ lật **cảnh chẵn**. Nên vùng che đúng ở cảnh lẻ và sai ở cảnh chẵn, nhìn thấy "nhảy" qua lại. Bản thân việc lật xen kẽ cũng làm nhân vật đổi hướng liên tục giữa các cảnh. Cần hỏi chủ dự án có cố ý như vậy không. Đề xuất: lật cả video hoặc không lật.

### A3. Zoom theo cảnh (`_video_scale`) chạy TRƯỚC bước làm mờ
- `video_editor.py:532-556`: scale + crop/pad theo từng cảnh, đặt trước blur.

### A4. Lệch 1–2px giữa `crop` và `overlay` trong `_build_blur_chain`
- `video_editor.py:996-1002`: phần cắt dùng toạ độ làm tròn xuống số chẵn `trunc(ih*y/2)*2`, nhưng `overlay` dán lại ở `H*y` không làm tròn. Kết quả là khối mờ trượt 1px và lộ một hàng điểm ảnh của chữ (đã đo được ở hàng cuối của chữ).

### Cách sửa A (đã thử nhanh: 4/6 test pass, phần còn lại do A4)
1. Tách `vf` trong `_process_one_scene` thành 2 phần:
   - `vf` = chỉ `scale…,pad…,fps` (đúng hệ toạ độ preview), cộng thêm `drawbox` che logo thủ công / `ai_logo_box`.
   - `vf_post` = `_video_scale` → `setpts` → `hflip` → color preset → `crop 0.97` → `tpad`.
   - Graph: `[0:v]{vf}[vbase]` → blur chain → `[last]{vf_post}[vgeo]` → Ken Burns/vignette → drawtext phụ đề mới → watermark.
   - Làm mờ trước `setpts` còn có lợi thêm: mốc `enable=between(t,…)` của blur box có thời gian vẫn tính theo giây gốc. Hiện tại ở Reup chúng bị lệch vì `setpts` đã kéo giãn hình.
2. Nhánh fallback (`fc_fb`, khoảng dòng 767-782) đang copy y nguyên graph hình. Nên dùng lại `filter_complex_v` để khỏi lệch hai nơi.
3. `_build_blur_chain`: mép trái/trên `trunc(…/2)*2`, mép phải/dưới `ceil(…/2)*2`, và `overlay` dùng đúng toạ độ đã cắt (`trunc(W*x1/2)*2`). Trong biểu thức `min(iw\,…)` nhớ escape dấu phẩy.
4. Nên có (tuỳ chủ dự án):
   - Nới vùng che thêm ~0.5% mỗi phía, vì viền/bóng chữ thường rộng hơn chỗ người dùng kéo.
   - Thêm kiểu che "mờ + tối" (`gblur` rồi `eq=brightness=-0.3`) hoặc nền đặc. Với chữ to, `gblur sigma=20` vẫn còn đọc được hình dạng chữ.
   - Tự dò vùng sub cứng: lấy ~30 khung, đo mật độ cạnh theo hàng ở 35% dưới khung (hoặc dùng PaddleOCR), đề xuất sẵn vùng che thay cho mặc định cứng `[10,84,80,10]`. Hiện `ai_sub_box`/`ai_logo_box`/`blur_boxes` không có nơi nào gán giá trị (code chết).

**Tiêu chí xong:** 5 test trong `test_cover_boxes.py` pass. Thử tay một video thật có sub cứng, bật lật gương + một preset màu: chữ gốc bị che kín ở mọi cảnh.

---

## B. Giọng đọc không sát timeline

### Cách các tool lồng tiếng làm (tham khảo pyVideoTrans, VideoLingo)
1. Nhận dạng giọng nói **có mốc theo từ** (WhisperX / `word_timestamps`) để mốc câu chính xác.
2. Dịch **từng câu**, giữ đúng số câu, kèm **ngân sách độ dài** theo thời lượng câu gốc.
3. **Cắt khoảng lặng đầu/cuối** file TTS trước khi tính độ dài.
4. Lời dài hơn câu gốc thì xử lý theo thứ tự:
   - (a) mượn khoảng lặng phía sau, cho tới câu kế tiếp;
   - (b) tăng tốc giọng, tối đa khoảng 1.3–1.5x;
   - (c) cuối cùng mới làm chậm hình một chút.
5. Lời **ngắn hơn** câu gốc thì **giữ hình tốc độ thường** và chèn lặng. Không bao giờ tua nhanh hình.

### B1. [Nghiêm trọng] Reup tua nhanh / làm chậm hình tới 2.5x để vừa với lời
- `video_editor.py:250` (`_pr = max(0.4, min(2.5, tts/clip))`) và `:513-515` (`pts_ratio`), `setpts` ở `:558`.
- Lời ngắn hơn câu gốc thì hình **tua nhanh** (đã đo: câu 4s, lời 1s, video gốc 6s xuất ra 2.6s). Lời dài hơn thì hình slow-motion. Kéo theo đó tiếng gốc (nhạc, SFX) cũng bị `atempo` theo.
- Preview frontend mô phỏng đúng logic sai này: `frontend/src/components/timeline/useTimelinePlayer.ts:40` và `Timeline.tsx:433`.
- **Sửa:** viết lại nhánh `is_reup` trong `build_review_video` (dòng 225-261) để tính sẵn cho từng câu, rồi `_process_one_scene` chỉ áp dụng kết quả, không tự tính lại. Cụ thể:
  - Khe = `[start, next_start)` (câu cuối thì tới hết video). `src = end - start`, `room = next_start - start`.
  - `tts ≤ src` → hình 1x dài `src`, lời đặt ở đầu, phần còn lại chèn lặng (`apad`).
  - `src < tts ≤ room` → hình 1x dài `tts` (mượn khoảng lặng sau), đoạn gap kế tiếp ngắn lại tương ứng.
  - `tts > room` → `atempo = min(1.35, tts/room)`; vẫn thiếu thì `setpts` chậm hình, tối đa khoảng 1.25x; vẫn thiếu nữa thì `tpad` giữ khung cuối. Ghi log những câu rơi vào trường hợp này để AI rút gọn lời.
  - Đoạn gap giữa các câu = phần còn lại của khoảng trống, tốc độ 1x, tiếng gốc.
  - Hai bên (`build_review_video` và `_process_one_scene`) phải dùng **cùng một** độ dài clip. Hiện tại mỗi bên tự tính một kiểu (xem B4).
  - Sửa `useTimelinePlayer.ts`/`Timeline.tsx` theo đúng mô hình mới để preview khớp video xuất.
  - Kiểm tra `qa.py:scene_fit`/`used_span` (`reup=True`) và `autofix.py`, vì chúng đang dựa trên giả định "kéo giãn hình".

### B2. [Nghiêm trọng] Reup gộp thoại thành block dài tới 12 giây
- `translator.py:3` `BLOCK_MAX_DUR = 12.0`, `BLOCK_MAX_CHARS = 220`; `_group_segments` (dòng 315) gộp mọi câu trong 12s, **bất kể khoảng lặng giữa chúng hay ai đang nói**.
- TTS đọc cả block một mạch từ đầu block, nên lời Việt không bám từng câu gốc: câu 2–3 trong block vang lên lúc nhân vật chưa nói hoặc đã nói xong. Đây là nguyên nhân lớn nhất của cảm giác "không sát".
- **Sửa:** chỉ gộp khi khoảng lặng giữa 2 câu < 0.3–0.4s **và** tổng ≤ ~6s **và** ≤ ~100 ký tự. Ngữ cảnh dịch vẫn giữ nhờ batch (`BATCH_BLOCKS`), không cần gộp câu. Cả nhánh Google miễn phí (`_translate_via_google_free`) cũng dùng `_group_segments`.

### B3. [Nghiêm trọng] Câu "hook" bị nhét vào câu thoại đầu ở Reup
- `translator.py:298-306`: `scenes[0]['voiceover'] = hook + ' ' + …`. Câu thoại 1 dài thêm cả một câu, nên cảnh đầu bị slow-motion nặng (với B1) hoặc lấn sang câu 2.
- **Sửa:** ở Reup không chèn hook vào thoại. Nếu muốn giữ hook thì cho nó thành một "cảnh" riêng đặt trong khoảng lặng trước câu đầu tiên (nếu đủ dài), hoặc bỏ hẳn.

### B4. SRT xuất kèm lệch so với video
- **`.vi.srt` sai hoàn toàn ở chế độ Review:** `pipelines.py:646` dùng `scenes_to_cues(run.job.scenes)`, nhưng `out_start/out_end` chỉ được ghi vào **bản sao** scene trong `build_review_video` (`_render` truyền vào `[dict(s) for s in job.scenes]`). Vì thế `srt_utils.py:90` rơi về `clip_start`, tức mốc của **video gốc**, không phải video xuất. (Chưa tái hiện bằng test riêng, nhưng thấy rõ từ code: grep `out_start` không có chỗ nào ghi lại vào job.)
- **`<tên>.srt` cạnh video (`_generate_srt_file`, `video_editor.py:287`) lệch vì 3 lý do:**
  - Reup: `out_end` tính theo `tts/clip` (dòng 250), không tính bước nén `atempo 1.18` trong `_process_one_scene` (dòng 503-515), nên lệch dồn theo từng câu dài (đã đo: 0.43s cho mỗi câu dài hơn câu gốc 1.5 lần).
  - Không cộng độ dài **intro** (dòng 370 chèn intro sau khi SRT đã ghi).
  - Không chia cho hệ số **tốc độ video** (dòng 402-417, `setpts/atempo` toàn bộ video sau khi ghi SRT).
- **Sửa:** sau khi dựng, đo độ dài thật từng clip (`_stream_duration(clip,'v:0')`), cộng dồn (tính cả intro), chia cho `_final_speed`, rồi mới ghi SRT. Trả `out_start/out_end` này về cho pipeline để `_write_job_srt` dùng (hoặc chỉ giữ một file SRT duy nhất).

### B5. File TTS không cắt khoảng lặng đầu/cuối
- `tts_engine.py`: Edge (dòng 255), CapCut, FPT đều lấy nguyên file. `tts_duration = _audio_duration(file)` (dòng 795) tính cả khoảng lặng đầu/cuối, thường 0.1–0.8s mỗi câu.
- Hậu quả: lời vào trễ so với miệng nhân vật; `tts_duration` dài giả nên kích hoạt kéo giãn hình hoặc tăng tốc không cần thiết; phụ đề chia theo độ dài giả nên lệch.
- **Sửa:** sau khi mọi engine trả kết quả (bọc `generate_tts_per_scene` lại, vì hàm có nhiều điểm `return`), chạy `silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:stop_threshold=-45dB`, hoặc `areverse` + `silenceremove` + `areverse` cho phần đuôi. Giữ lại ~30ms ở đầu và ~100ms ở đuôi, ghi ra `.wav`, cập nhật `tts_path`/`tts_duration`. Câu tạo lại (`regenerate_scene`, `_auto_fix.synth`, `_fill_missing_voices`) cũng đi qua `synthesize`, nên sẽ được xử lý luôn.

### B6. Mốc câu từ Whisper chưa chính xác
- `transcriber.py:297-302`: không bật `word_timestamps`. Mốc đoạn của faster-whisper khi không có mốc theo từ thường dư vào khoảng lặng hoặc vào sớm. Nên bật `word_timestamps=True` và lấy `start` từ từ đầu, `end` từ từ cuối của mỗi đoạn. Có thể tách đoạn dài ở chỗ lặng > 0.5s giữa các từ.
- `initial_prompt` bằng tiếng Việt ("Dưới đây là đoạn phim…", dòng 301 và 192) trong khi audio là tiếng Trung/Hàn. Prompt kiểu này dễ kéo Whisper ra chữ sai ngôn ngữ hoặc ảo giác. Nên bỏ, hoặc chọn prompt theo ngôn ngữ nguồn.

### B7. Bản dịch không có ngân sách độ dài
- Prompt Việt hoá (`translator.py:595`) chỉ ghi "giữ độ dài xấp xỉ bản gốc". Nên đưa vào từng dòng `dur` (giây) và `max_am_tiet ≈ dur × tốc_độ_giọng` (đo bằng `postedit.measure_wps`, CapCut ~4.4, Edge ~3.8 từ/giây) và yêu cầu không vượt.
- Sau TTS, câu nào vẫn vượt `room` (xem B1) quá 1.35x thì gửi lại AI rút gọn, có thể dùng lại `postedit.rewrite_to_length`.

### B8. Tự hậu kỳ chạy logic của Review trên job Reup
- `pipelines.py:487,532` gọi `fix_durations` cho cả Reup. Hàm này sửa `clip_end` của câu thoại, tức làm sai mốc câu gốc. Với Reup nên bỏ qua (mô hình B1 đã tự xử lý).
- `suggest_edits` có thể đặt `exclude` cho một câu thoại. Khi đó câu đó biến thành đoạn gap với `orig_volume = 1.0` (`video_editor.py:240`), và **tiếng gốc nước ngoài vang to**. Ở `_step_edit` (dòng 417), câu bị xoá trắng cũng gặp đúng chuyện này. Đề xuất: Reup không cho AI bỏ câu. Nếu người dùng tự bỏ câu thì đoạn đó giữ âm lượng `original_volume`.

### B9. Phụ đề trong cảnh chia theo số ký tự, không theo giọng thật
- `video_editor.py:663-671` và `_generate_srt_file` chia thời gian theo tỉ lệ ký tự. Edge TTS có sự kiện `WordBoundary` (lấy qua `Communicate.stream()`) cho mốc từng từ. Nên lưu mốc này vào scene (vd `_word_times`) để chia đoạn phụ đề đúng lúc giọng đọc tới. Engine nào không có mốc theo từ thì giữ cách chia theo ký tự.

### B10. Review: lời kể nói về cả chương, nhưng hình chỉ chiếu vài giây đầu chương
- Ở chế độ V2, khung hình đưa cho Vision AI rải khắp chương (`story_analyzer.py:328,381`). Nhưng số từ mỗi cảnh bị ép theo ngân sách, tối thiểu 12 từ (`script_writer.py:257-270`). Còn video_editor chỉ cắt `clip_start .. clip_start + tts_duration` và bỏ qua `clip_end` (`video_editor.py:519-527`).
- Ví dụ: phim 100 phút làm review 12 phút cho ra khoảng 232 chương, mỗi chương ~26s nhưng chỉ ~12 từ, tức ~3s lời. Lời kể chuyện xảy ra ở giây 8–17 của chương, nhưng phần hình đó không bao giờ được chiếu.
- **Sửa (chọn 1):**
  - chỉ lấy khung hình cho Vision trong `[cs, cs + tts dự kiến]`;
  - hoặc khi dựng, ghép nhiều đoạn nhỏ trải đều `[clip_start, clip_end]` (jump-cut);
  - hoặc giới hạn số chương theo ngân sách từ.

### B11. Review: lời dài hơn đoạn hình thì tràn sang hình của cảnh sau, rồi cảnh sau chiếu lại đoạn đó
- `video_editor.py:519-527` cắt theo `tts_duration` và không chặn tại `clip_start` của cảnh kế tiếp. Ngưỡng `fix_durations` chỉ chạy khi lệch quá 2.5x (`postedit.py:248-253`).
- Ví dụ: cảnh 6s, lời 8s → chiếu thêm 2s đầu của cảnh sau, rồi cảnh sau lại chiếu từ đầu → **lặp hình**.
- **Sửa:** hình của cảnh = `min(tts, next_start - clip_start)`, phần lời còn dư thì chiếu chậm lại một chút hoặc giữ khung cuối. Tự hậu kỳ nên viết lại mọi cảnh có lời dài hơn hình quá ~1.05x.

### B12. Review: các nhánh dự phòng âm thầm ghép sai lời với cảnh
- Nếu dưới 70% nhãn `[Cảnh N]` đọc được, `script_writer.py:366-369,378-382,409,421` chia đều số từ cho các cảnh. Nếu không có nhãn nào, nó ghép đoạn văn theo thứ tự.
- `_fallback_plain_text` còn không yêu cầu AI ghi nhãn, nên lần nào cũng rơi vào các nhánh trên. Chỉ có một dòng WARN trong log.
- Hệ quả thêm: mô tả giả như "Phan 3 trong 60" hay "Canh 5" có thể bị đọc thành lời (`script_writer.py:158,171,392`, `story_analyzer.py:260`).
- **Sửa:** yêu cầu nhãn ở cả nhánh dự phòng; thiếu nhãn thì hỏi lại AI hoặc báo lỗi, không chia đều. Không bao giờ dùng mô tả giả làm lời đọc.

### B13. Review: các lỗi nhỏ hơn về kịch bản
- Mốc thời gian beat Gemini trả về không được đối chiếu với mốc khung hình thật. Nếu AI trả số thứ tự khung, hoặc chuỗi "12s" (`_safe_float` thành 0), cảnh nhận khoảng thời gian rác (`script_writer.py:159-194`).
- AI hậu kỳ không được xem mô tả cảnh mà vẫn bị yêu cầu "thêm chi tiết của chính cảnh đó", nên dễ bịa (`postedit.py:80-92`). V2 còn bỏ hẳn `description` (`script_writer.py:518`).
- Thoại cuối phim bị cắt khỏi prompt Vision vì giới hạn cứng 8000 ký tự (`gemini_analyzer.py:156-160`).
- Tốc độ đọc cố định 230 từ/phút lúc viết kịch bản, trong khi giọng thật khác nhau (CapCut ~4.4, Edge ~3.8 từ/giây). Nên dùng `measure_wps` hoặc bảng tốc độ theo từng giọng.
- Khung hình V1 bắt đầu từ 5% phim, nên đoạn mở đầu không bao giờ được kể.

---

## C. Âm lượng bị tụt (giọng nhỏ dần, tiếng phim lúc to lúc nhỏ)

### C1. `amix` mặc định chia âm lượng cho số input — đã đo được
- Mặc định `amix` có `normalize=1`: mỗi input bị nhân với trọng số của nó / tổng trọng số. Đo thực tế:
  - Thêm nhạc nền (`_mix_bgm`, `video_editor.py:444-446`): **giọng −6 dB**, kể cả khi nhạc câm.
  - SFX/nhạc từ Timeline (`_mix_multi_audio`, `:484`, `inputs=N+1`): có 4 SFX thì **giọng −14 dB** trong lúc SFX phát, rồi to trở lại khi SFX hết. Nghe như giọng bị "nuốt".
  - Trong cảnh (`:758`, `weights=1 3`): giọng −2.5 dB. Ở Reup, đoạn không thoại có `orig_volume=1.0` nhưng ra **−12 dB** (chỉ còn 1/4). Kết quả: lúc có thoại thì tiếng phim tắt, lúc không thoại thì nhỏ, âm lượng chênh nhau rõ.
- **Sửa:** thêm `normalize=0` cho mọi `amix` và tự đặt `volume` cho từng input. Cuối chuỗi xử lý thêm `alimiter` (hoặc `loudnorm=I=-16:TP=-1.5`) để không bị vỡ tiếng.

### C2. Không chuẩn hoá độ to
- Giọng từ CapCut, Edge, FPT, VieNeu có độ to khác nhau. Câu đọc lại bằng engine khác (fallback) sẽ to/nhỏ khác hẳn câu bên cạnh. Nên chạy `loudnorm` từng file TTS (khoảng −16 LUFS) khi cắt lặng (B5).
- Mọi bước đều xuất `-ac 1` (mono), nên tiếng phim stereo bị gộp thành mono (ưu tiên thấp).

---

## D. Giọng gắn nhầm cảnh / cảnh bị lặp

### D1. Tự hậu kỳ gắn giọng mới vào sai cảnh — đã tái hiện
- `pipelines.py:518` gửi lô `{…, '_original_index': i}`, nhưng `generate_tts_per_scene` ghi đè luôn: `s['_original_index'] = idx` (`tts_engine.py:131`, idx = vị trí trong lô).
- Ví dụ: AI sửa cảnh [1, 3] → cảnh 1 nhận giọng của cảnh 3, còn cảnh 3 bị coi là lỗi và trả về lời cũ. Sửa cảnh [4, 7] → cả hai bị coi là lỗi dù TTS chạy thành công.
- **Sửa:** `s.setdefault('_original_index', idx)`, hoặc ghép kết quả theo vị trí trong lô.

### D2. Phân vai nhiều giọng: cả video lặp đôi — đã tái hiện
- `generate_tts_multi_voice` (`tts_engine.py:787`) trả về `dict(s)` không có `_original_index`. `_fill_missing_voices` (`pipelines.py:451`) vì thế thấy `got = {-1}`, coi mọi cảnh là thiếu, đọc lại hết bằng một giọng, rồi trả về `rendered + fixed`.
- Kết quả: 3 cảnh thành 6, video chạy hết rồi **lặp lại toàn bộ bằng một giọng**.
- **Sửa:** gán `s2['_original_index'] = i`; trong `_fill_missing_voices` loại bản trùng theo chỉ số.

### D3. Sửa "Lời đọc" mà không tạo lại giọng thì vẫn xuất giọng cũ
- `PostEditor.tsx:470` chỉ cập nhật chữ. `_step_preview` (`pipelines.py:546`) nhận nguyên scene từ client. Video ra có phụ đề mới nhưng giọng đọc câu cũ, không có cảnh báo nào. Nếu `regenerate` lỗi thì chữ cũng không được trả lại như cũ (`:633`).
- **Sửa:** lưu `tts_text` (đúng câu đã đọc) lúc tạo giọng. Thêm check mức lỗi trong `checks.ts` khi `voiceover !== tts_text`. Khi xác nhận xuất, đọc lại hoặc chặn những cảnh lệch.

### D4. Kết quả `regenerate()` ghi theo vị trí mảng, dễ lệch nếu đổi thứ tự lúc đang chờ
- `PostEditor.tsx:130-137`: trong lúc đang chờ TTS, người dùng vẫn kéo đổi thứ tự hay undo được. Giọng mới khi về sẽ gắn vào cảnh đang đứng ở vị trí `i`. Tự hậu kỳ chạy tới 8 yêu cầu song song nên dễ gặp. **Sửa:** mỗi cảnh có id cố định, ghép kết quả theo id.

### D5. VieNeu dùng lại file giọng cũ
- Đường dẫn file cố định `audio/vo_{i:04d}.wav` và không bị xoá trước khi chạy (`tts_engine.py:605,639-656`). Khi bấm "Tiếp tục" sau khi đã sửa hoặc đổi thứ tự kịch bản, câu nào worker đọc lỗi sẽ dùng nhầm file cũ (lời cũ, có thể của cảnh khác). **Sửa:** mỗi lần chạy dùng một thư mục riêng.

### D6. Phân vai: thường bị tắt âm thầm, ghép lỗi thì mất lời
- `casting.py:474` nối các đoạn bằng `''.join` (mất khoảng trắng), nên phép so với câu gốc gần như luôn sai → âm thầm quay về giọng người kể.
- Ghép audio lỗi thì chỉ giữ `paths[0]` (`tts_engine.py:781-783`): mất phần lời còn lại, trong khi phụ đề vẫn hiện đủ câu. Nên báo lỗi hoặc quay về một giọng.

---

## E. Phụ đề

### E1. Có `%` trong lời là cảnh bị bỏ khỏi video — đã tái hiện
- `drawtext` mặc định `expansion=normal`, tức là coi `%` là ký tự lệnh. "Giảm 50% giá" → ffmpeg báo `Stray %`. Lần thử lại dùng cùng filter nên cũng lỗi, `_process_one_scene` trả False, rồi `build_review_video` chỉ log "Bỏ qua cảnh" (`video_editor.py:353`). **Video thiếu cảnh, mọi câu sau đó lệch phụ đề so với SRT.**
- **Sửa:** thêm `expansion=none:` vào drawtext (`:703`). Cảnh bị bỏ phải làm job lỗi, hoặc ít nhất QA phải báo.
- Cùng chỗ đó, nhánh thử lại (`:766`) không log stderr của lần chạy đầu, và **âm thầm bỏ tiếng gốc**. Cần log lỗi gốc, và chỉ thử lại khi đúng lý do cần thử lại.

### E2. `_fit_subtitle` không giữ đúng số dòng tối đa
- `video_editor.py:1022-1025`: thu cỡ chữ tới `min_font` mà vẫn không vừa thì vẫn trả về 3–4 dòng. Đã thử: video 1080x1920, cỡ chữ ×1.5 ra 3 dòng, ×2.0 ra 4 dòng. Ước lượng độ rộng 0.6×cỡ chữ cũng hụt với chữ IN HOA (thực tế ~0.68). **Sửa:** chia lại đoạn khi còn vượt số dòng; dùng hệ số 0.7 cho chữ in hoa.

### E3. Xem trước khác với video xuất
- Nguồn chữ: preview hiện `subtitle || voiceover` (`PostEditor.tsx:326`), còn khi xuất dùng `sub_source` (mặc định là voiceover). Ở Reup hai trường này thường khác nhau.
- Độ dài đoạn: preview chia `max_chars × max_lines` = 112 ký tự (`PostEditor.tsx:62`), backend chia 56.
- Thời gian: preview chia đều thời gian giữa các đoạn, backend chia theo số ký tự.
- Kiểu chữ: `Monitor.tsx:97` dùng `line-clamp-2` (che mất lỗi E2), không áp màu/cỡ/in hoa/font đã chọn. `SubtitlePreview` cỡ cố định 17px, chữ đậm, trong khi drawtext dùng font Regular.
- **Sửa:** dùng chung một luật chia đoạn (frontend nhận `sub_max_chars_per_chunk` từ backend, chia thời gian theo ký tự), chọn chữ theo `sub_source`, áp đúng kiểu chữ.

### E4. Hai đường ghép phụ đề cho cỡ chữ khác nhau
- "Ghép phụ đề" dùng ASS `FontSize = 16 × hệ số` trên PlayResY 288, tức ~5.6% chiều cao khung (`pipelines.py:800`). Review/Reup dùng drawtext h/26, tức ~3.85%. Cùng một preset mà to hơn ~45%. **Sửa:** FontSize ≈ 11 × hệ số.

### E5. Lỗi nhỏ
- `between(t,a,b)` tính cả hai đầu mút, nên tại ranh giới giữa hai đoạn, cả hai cùng hiện trong 1 khung. Dùng `gte(t,a)*lt(t,b)`.
- `fmt_ts` có thể ra `00:00:60,000` (không hợp lệ) với 59.9996s (`srt_utils.py:12`). Làm tròn ms trước khi tách giờ/phút/giây.
- `_generate_srt_file` ngắt dòng ở 28 ký tự nên có câu ra 3 dòng.
- Font không tìm thấy thì âm thầm lấy font mặc định, không log (`_find_system_font:161`). Không kiểm font có đủ dấu tiếng Việt không.

---

## F. QA / tự sửa

- `autofix.py:28-36` `scene_at` giả định mỗi cảnh dài đúng `tts_duration`. Sai với Reup (có đoạn không thoại, có kéo giãn) và khi có chuyển cảnh, nên **sửa nhầm cảnh**. **Sửa:** dùng `out_start/out_end` thật từ bước dựng (cùng việc với B4).
- Hoàn tác một vòng tự sửa thì khôi phục mp4 và `.vi.srt`, nhưng không khôi phục `<tên>.srt` / `.ass` (`autofix.py:237-240`, `pipelines.py:667-670`).
- QA phụ đề (`qa.py:290-296`) chỉ đếm dòng trong file SRT, không kiểm phụ đề có thực sự được ghép vào video không. Kiểm độ dài ±10% cũng không bắt được một cảnh bị bỏ (E1). **Nên thêm:** so số clip dựng được với số cảnh.
- `qa.py:scene_fit`/`used_span` cho Reup đang dựa trên mô hình "kéo giãn hình" của B1, cần làm lại cùng B1.

---

## G. Đọc số và engine TTS

### G1. Đổi số thành chữ sai — đã chạy thử `replace_numbers_with_words`
| Vào | Ra hiện tại | Nên là |
|---|---|---|
| `gọi 0912345678` | chín trăm mười hai triệu… | không chín một hai… (đọc từng số) |
| `tập 1,2,3` | một trăm hai mươi ba | một, hai, ba |
| `cao 2,500 mét` | hai nghìn năm trăm | hai phẩy năm (dấu phẩy thập phân kiểu VN) — cần quy ước |
| `1.005.000 đồng` | một triệu năm nghìn | một triệu không trăm lẻ năm nghìn |
| `năm 2024` | hai nghìn hai mươi bốn | hai nghìn không trăm hai mươi tư |
| `giảm 50%` | năm mươi% | năm mươi phần trăm |
| `lúc 10:30` | mười:ba mươi | mười giờ ba mươi |

`tts_engine.py:29-115`. Phụ đề ở Reup cũng hiện các chữ này, vì `translator.py` gán `subtitle = text` sau khi đã đổi số.

### G2. Engine
- CapCut bỏ qua tốc độ đọc: `rate` không được truyền vào `synthesize_batch` (`tts_engine.py:403`). Ngoài ra code giả định CapCut trả kết quả đúng thứ tự (chưa chắc).
- Worker VieNeu có thể treo vĩnh viễn và giữ khoá GPU: chỉ kiểm hạn giờ khi có dòng stdout mới (`tts_engine.py:621-626`). **Sửa:** đọc stdout trong thread riêng, hoặc `proc.wait(timeout)` + kill.
- Edge chỉ log lỗi thật của cảnh 0 (`:263`), các cảnh khác chỉ báo "thất bại" không có lý do.
- `_audio_duration` / `get_video_duration` trả 0.0 khi lỗi (`tts_engine.py:795-801`, `utils.py:102-108`), nên cảnh bị bỏ với lý do "quá ngắn", che mất nguyên nhân thật.

---

## H. Khác

- **Whisper và audio vào trễ (chưa chắc):** file TS/HLS có luồng audio bắt đầu muộn hơn video. Trích wav thì mất khoảng trễ đó, nên mọi mốc Whisper sớm hơn hình đúng bằng khoảng trễ (`transcriber.py:69`). **Sửa:** dò `stream=start_time` của audio và video rồi cộng phần chênh vào mốc, hoặc trích bằng `aresample=async=1:first_pts=0`.
- **Preview lệch dần:** `useTimelinePlayer.ts:101-150` chỉ đồng bộ video lúc bắt đầu clip, và chỉ khi lệch quá 0.25s; trong clip không chỉnh lại. File giọng lỗi 404 thì đầu phát đứng im ở đầu clip.
- **Hằng `TAIL 0.12s` của Review không có tác dụng:** `-t tts_duration` ở đầu ra cắt mất (`video_editor.py:524` và `:755`). Đây là code chết.
- **Khoá cache clip bỏ qua các trường bắt đầu bằng `_`** (`video_editor.py:323`), trong đó có `_video_scale`, `_manual_sub_chunks`. Hiện chưa có chỗ nào sửa các trường này, nhưng nếu sau này cho sửa thì sẽ dùng nhầm clip cũ trong cache.
- **Bản nháp:** sau khi xác nhận, một lần lưu nháp đến muộn có thể tạo lại bản nháp cũ (`useDraft.ts:32`, `router.py:188`).
- **Downloader:** đọc hết stdout rồi mới đọc stderr, nên yt-dlp có thể treo nếu stderr đầy bộ đệm (`downloader.py:310-328`). `download_direct` luôn đặt đuôi `.mp4`, và hai lượt tải cùng tên đè file của nhau.
- **Kiểu dữ liệu:** `_process_one_scene(video_total_duration=0)` nên đổi mặc định thành `0.0`, vì code thật luôn truyền float (Pyright báo lỗi ở mọi chỗ gọi).

---

## Thứ tự làm đề xuất

1. **D1, D2, E1** — sửa ít dòng, đang **hỏng video âm thầm** (gắn nhầm giọng, lặp đôi cả video, mất cảnh vì `%`).
2. **C1** (`amix normalize=0` + limiter) — sửa vài dòng, hết hiện tượng giọng nhỏ đi và âm lượng phim chênh nhau.
3. **A1–A4** (vùng che) — khoanh vùng trong `_process_one_scene` và `_build_blur_chain`.
4. **B5 + C2** (cắt lặng + chuẩn hoá độ to TTS) — lợi cho cả Review lẫn Reup.
5. **B2 + B3** (không gộp block 12s, bỏ hook ở Reup) — hiệu quả lớn nhất với lỗi Reup "không sát".
6. **B1** (mô hình căn thời gian Reup mới) + preview frontend + `qa.py`/`autofix.py` (F). Phần này lớn nhất.
7. **B10, B11** (Review: hình khớp lời, không lặp hình), **D3** (lời sửa mà giọng cũ).
8. **B4** (SRT), **B8**, **E2–E4**, **G1**.
9. Phần còn lại (B6, B7, B9, B12, B13, D4–D6, E5, G2, H).

Mỗi bước: chạy `python -m pytest tests -q`, rồi dựng thử một tập phim thật ngắn (2–3 phút, có sub cứng) ở cả Review và Reup.

## Đã kiểm, KHÔNG phải lỗi
- Ghép thường (`_concat_clips`) 60 clip có độ dài lẻ khung: hình và tiếng cuối video lệch dưới 1 khung, không lệch cộng dồn.
- Ken Burns (zoompan) đã đặt sau bước làm mờ, nên vùng che zoom theo hình là đúng.
- Ghép có chuyển cảnh (`_concat_with_transitions`) đã kéo dài khung cuối nên không làm ngắn video.
- Escape đường dẫn `fontfile`/`textfile` trên Windows và `\,` trong `enable` đều đúng; dấu `\` và `"` trong lời không làm hỏng cảnh (đã thử).
- Mốc khung hình đưa vào prompt Vision khớp với khung đã trích; khung lỗi bị bỏ ở cả hai nơi.
- `sub_max_lines` vẫn được truyền vào bước dựng qua `**run.layout`.
- Cảnh bị loại được lọc trước cả bước dựng lẫn QA, nên chỉ số cảnh của QA khớp với `job.scenes`.

## Tham khảo
- pyVideoTrans, thuật toán căn tiếng/hình/phụ đề: https://en.pyvideotrans.com/blog/audio-subtitles-video-sync. Cắt lặng đầu/cuối lời lồng tiếng trước khi tính; khi thiếu thời gian thì chia phần dư cho cả hai: giọng tăng tốc tối đa ~1.5x, phần còn lại làm chậm hình; giọng ngắn hơn thì chèn lặng; khoảng trống < 50ms gộp vào clip kề bên.
- VideoLingo: mốc phụ đề theo từ bằng WhisperX, dịch theo ngữ cảnh rồi cắt/căn câu trước khi lồng tiếng.
