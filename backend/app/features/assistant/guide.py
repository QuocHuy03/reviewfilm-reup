"""Cẩm nang ReviewFilm Studio cho Trợ lý AI — viết theo đúng giao diện hiện tại (bản 2.7.0).

Chỉ ghi những gì có thật trong app. Đổi giao diện / thêm tính năng thì cập nhật ở đây.
"""

APP_GUIDE = """
# CẨM NANG REVIEWFILM STUDIO (bản 2.7.0)

App desktop biến phim dài thành video review / dịch & reup có thuyết minh + phụ đề.
AI (xem phim, viết kịch bản, dịch, phân vai, bài đăng) chạy bằng TÀI KHOẢN ChatGPT / Gemini web đăng nhập trong app — không cần API key OpenAI/Gemini.
Job chạy theo hàng đợi, mỗi lúc 1 job nặng; job đang chờ bạn sửa kịch bản / xem trước sẽ nhường lượt cho job sau.

## THANH BÊN TRÁI (thứ tự từ trên xuống)
- Tổng quan · Tải video · Tạo video · Studio · Lịch sử · Phụ đề · Giọng đọc
- Dưới cùng: Hỗ trợ (mở taothaoai.com — hướng dẫn, báo lỗi, liên hệ) và Cài đặt (biểu tượng bánh răng).
- Thanh trên cùng: nút job đang chạy (bấm để mở job trong Studio), đồng hồ CPU/RAM/GPU, nút sáng/tối, nút Trợ lý AI.

## ĐĂNG NHẬP TÀI KHOẢN AI (quan trọng nhất)
Cài đặt → tab "Tài khoản AI":
- ChatGPT: bấm "Thêm tài khoản" → cửa sổ Chrome mở ra → đăng nhập chatgpt.com → bấm "Đã đăng nhập xong" (hoặc đóng cửa sổ). Có nút "Kiểm tra" (gửi thử 1 câu), ngôi sao = chọn tài khoản đang dùng, thùng rác = xoá.
- Gemini: bấm "Đăng nhập Google" → đăng nhập trong cửa sổ Chrome, app tự nhận (tối đa 5 phút). Có "Kiểm tra", "Đăng xuất".
- Chế độ Review BẮT BUỘC đăng nhập Gemini (Gemini xem hình ảnh phim). Dịch & Reup, Dịch phụ đề, Tách SRT không đăng nhập vẫn chạy (dùng Google dịch miễn phí).
- Chỉ dùng được trong app desktop (Electron).

## TỔNG QUAN (Home)
- Thẻ lối tắt: Tải video, Tạo review phim, Dịch & Reup, Dịch phụ đề, Phụ đề, Giọng đọc.
- "Job gần đây" (bấm để mở trong Studio) và khung "Hệ thống": số video hoàn thành, GPU, ổ đĩa xuất còn trống (báo vàng khi < 3 GB), tài khoản AI, ffmpeg/ffprobe.
- Chưa đăng nhập AI thì có nút "Đăng nhập tài khoản AI" dẫn tới Cài đặt.

## TẢI VIDEO
1. Dán link vào ô "Dán link video" — mỗi dòng 1 link; dán nguyên đoạn chia sẻ Douyin/TikTok cũng được, app tự lấy link.
2. Chọn chất lượng: Tốt nhất / 1080p / 720p / Chỉ âm thanh.
3. Tuỳ chọn: "Tạo phụ đề (kèm bản dịch Việt)" — chọn ngôn ngữ gốc Trung/Anh/Hàn/Nhật (dùng CapCut); công tắc "Lưu poster".
4. "Lưu vào": bấm "Đổi" để chọn thư mục (app nhớ lần trước); bấm X để về mặc định = <Thư mục xuất trong Cài đặt>\\Downloads.
5. App tự xem trước link (ảnh bìa, nền tảng, thời lượng, độ phân giải). Bấm ảnh bìa để xem poster phóng to (có nút "Lưu poster"); nút "Poster" lưu ảnh bìa nét nhất vào Downloads/Poster.
6. Bấm "Tải video" / "Tải N video".
- Phim ngắn (DramaBox, GoodShort, ShortMax, NetShort, FreeReels, KissKH, Hồng Quả, DramaWave, RaptDrama, FlexTV, StardustTV): 1 link = cả bộ. Ô "Tập:" chọn tập, vd 1-10,15; để trống = tất cả. Tải 3 tập song song.
- Nền tảng hỗ trợ (không cần đăng nhập): Douyin, Bilibili, Weibo, AcFun, Youku, Tencent Video, Mango TV, Huya, TikTok, YouTube, Instagram, Pinterest, Dailymotion, Twitch, link .mp4 trực tiếp.
- Thư mục gọn kiểu Plex/Kodi: phim nhiều tập → Downloads/<Tên phim>/ (poster.jpg, Thông tin phim.txt, EP01.mp4…); video lẻ → Downloads/<Nền tảng>/ (kèm <tên>-poster.jpg).
- Mục "Đang tải & đã tải": phim nhiều tập gom thành 1 khối (poster, số tập, dung lượng) — bấm tên để xem từng tập.
  Mỗi video có nút Review / Reup / Dịch phụ đề (mở Tạo video với video đó); "Làm cả bộ (N)" / "Làm hàng loạt (N)" đưa cả lô sang Tạo video → Nhiều video;
  "Tải lại N lỗi" chỉ tải lại mục lỗi; ô "Tìm phim / video…"; "Dừng" khi đang tải; X = ẩn khỏi danh sách; "Dọn" = ẩn mọi job đã xong (file vẫn giữ nguyên).

## TẠO VIDEO
Trên cùng chọn chế độ: "Tạo Review" · "Dịch & Reup" · "Dịch phụ đề". Góc phải có "Mẫu kênh" (lưu/áp dụng toàn bộ cấu hình trừ video nguồn: giọng, phụ đề, logo, intro/outro…; "Lưu thành mẫu", trùng tên thì ghi đè).
Form tự lưu — chuyển trang không mất.

### Video nguồn
- "File": chọn 1 file video (.mp4, .mkv, .mov…). "Nhiều video": mỗi dòng 1 file (cần ≥ 2), nút "Chọn nhiều file"; chạy lần lượt, TỰ ĐỘNG HOÀN TOÀN (không dừng chờ sửa).
- Không còn ô nhập link URL: video trên mạng thì tải ở trang Tải video rồi bấm Review/Reup/Dịch phụ đề hoặc "Làm hàng loạt".
- Ngôn ngữ video gốc (Tự động, Trung, Anh, Nhật, Hàn, Việt) · Whisper model (capcut = online nhanh nhất ~10s/tập, cần mạng; tiny/base nhanh; small/medium/large chính xác hơn) · Thiết bị xử lý (GPU NVIDIA / CPU — máy không có GPU NVIDIA thì chọn CPU).
- "Cắt khung hình": cắt bỏ hẳn dải phụ đề cứng / logo / viền ở mép rồi phóng cho đầy khung.
- "Tự che mọi chữ tiếng Trung (AI quét)": tắt (mặc định) chỉ che phụ đề cũ + chữ/logo 4 góc; bật thì AI che mọi chữ Trung trên hình đúng lúc chữ hiện (tốn thêm thời gian quét, chỉ lần đầu).
- Riêng Dịch phụ đề: "Video gốc có phụ đề Trung in sẵn" (bật = đọc phụ đề trên hình làm lời gốc và xoá phụ đề cũ; tắt = nghe giọng bằng Whisper), "Hiện phụ đề tiếng Việt trên video", "Lồng tiếng Việt" (tắt = chỉ ghép phụ đề, giữ tiếng gốc).

### Các tab cấu hình (chấm màu trên tab = đang có tuỳ chọn khác mặc định)
- Kịch bản (Review) / Bản dịch (Reup, Dịch phụ đề):
  Review: "Độ dài review" = Tự động theo video (phim 20′ → ~8′, 90′ → ~13′, 2 giờ → ~16′) / Ngắn ~8′ / Vừa ~12′ / Dài ~18′ / Tuỳ chỉnh; "Phân tích chuyên sâu" (cắt cảnh theo scene thật, khớp hình hơn, chậm hơn).
  Reup/Dịch phụ đề: "Dịch bằng AI (ChatGPT / Gemini)" — chưa đăng nhập thì dùng Google dịch.
  "Bối cảnh phim (tuỳ chọn)": tên phim, thể loại, tên nhân vật → AI viết/dịch đúng tên riêng hơn.
- Giọng đọc (Review/Reup): chọn giọng, "Tốc độ video & giọng" (0.85x … 1.3x), Review có "Phân vai nhiều giọng" (AI nhận diện nhân vật, mỗi vai 1 giọng VieNeu; cần ChatGPT hoặc Gemini).
- Lồng tiếng (Dịch phụ đề): "Giọng riêng cho nhân vật nam / nữ" (tắt = 1 giọng cho mọi nhân vật); "Tuỳ chọn nâng cao": "Tách giọng gốc, giữ nhạc nền" (tải model ~64MB lần đầu), "Tiếng gốc khi có lời Việt" (%), "Chỉ lồng câu có phụ đề Trung trên hình".
- Phụ đề: "Ghép phụ đề vào video", Phong cách (Mặc định chữ trắng viền đen, các kiểu CapCut, Bản tin…), Bố cục dòng (1 dòng rất ngắn / 2 dòng gọn — khuyên dùng / 3 dòng), Nguồn phụ đề (Theo lời đọc AI / Theo subtitle/dịch gốc), Cách đáy %, chỉnh màu/cỡ chữ chi tiết.
  "Che phụ đề gốc / logo": kéo khung ngay trên khung hình, có nút tự dò vùng phụ đề cũ; "Phụ đề mới nằm giữa vùng che".
  Kiểu che (Review/Reup): Làm mờ (như Review) / Xoá nhẹ / Xoá sạch nét chữ (chỉ có ở Dịch phụ đề).
  Dịch phụ đề: "Che phụ đề cũ" = Nhanh (khuyên dùng) hoặc Xoá sạch nét chữ (đẹp nhất nhưng rất chậm ~1–1.5 phút / 1 phút video); "AI tự căn vùng che khi dựng".
- Hiệu ứng (không có ở Dịch phụ đề): Chuyển cảnh (Mờ dần, Hoà tan, Qua màn đen, Trượt, Phóng to, Ngẫu nhiên…), Màu phim (Điện ảnh, Lạnh, Rực rỡ, Cổ điển…), Zoom chậm (Ken Burns), Tối viền. Không làm lệch lời/phụ đề.
- Hậu kỳ (không có ở Dịch phụ đề): "Tự hậu kỳ sau khi lồng tiếng", "Tự kiểm tra & sửa lỗi sau khi xuất", "Tự viết bài đăng sau khi xuất", "Lật ảnh xen kẽ", "Khung hình xuất" (16:9 1080p / 16:9 720p / 9:16 Shorts/TikTok), Logo/watermark (góc, cỡ, độ rõ — nên dùng PNG nền trong suốt), Intro / Outro.
- Quy trình: "Chạy hoàn toàn tự động", "Xem & sửa kịch bản trước khi lồng tiếng", "Nghe lại & xác nhận trước khi dựng video", "Thư mục xuất"; Dịch phụ đề có thêm "Khung hình xuất" (9:16: video ngang nằm giữa, viền đen trên/dưới).
- Cột phải: xem trước khung hình + phụ đề mẫu, tóm tắt cấu hình, khung "Cần kiểm tra" (lỗi chặn bắt đầu), nút "Bắt đầu tạo review" / "Bắt đầu dịch & reup" / "Bắt đầu dịch & lồng tiếng" / "Bắt đầu dịch phụ đề".

### Quy trình từng chế độ
- Review: Whisper nhận dạng lời → Vision AI (Gemini) xem phim → viết kịch bản → (dừng "Sửa kịch bản thuyết minh" nếu bật) → lồng tiếng → tự hậu kỳ → (dừng "Hậu kỳ & xác nhận" nếu bật) → dựng video → kiểm tra chất lượng, bài đăng.
- Dịch & Reup: Whisper → dịch → lồng tiếng thuyết minh bám miệng nhân vật (hình chạy tốc độ thật) → dựng video.
- Dịch phụ đề: nhận dạng / đọc phụ đề cứng → dịch → (dừng "Sửa bản dịch") → che phụ đề cũ & ghép phụ đề Việt (+ lồng tiếng nếu bật) → xuất video + .srt.

## STUDIO (xem & sửa job)
- Thanh tiêu đề job: loại job + tên, "Chỉnh thông số" (mở lại Tạo video với đúng video & thông số để sửa rồi chạy lại; hỏi dừng job cũ nếu còn chạy), nút Dừng (vuông đỏ), mở thư mục kết quả, Nhật ký (biểu tượng cuộn giấy; chấm đỏ khi job lỗi), Toàn màn hình (phím F, Esc để thoát).
- Đang chạy: xem từng bước + tiến độ; các cảnh hiện dần khi có kịch bản/bản dịch.
- Bước "Sửa kịch bản thuyết minh" (Review) / "Sửa bản dịch" (Dịch phụ đề) / "Duyệt kịch bản theo vai": sửa từng câu, đổi nhân vật từng câu, đổi "Giọng từng nhân vật", xoá câu; câu báo "đọc hơi nhanh" / "dài quá, AI sẽ rút gọn". Bấm "Xác nhận & lồng tiếng" hoặc "Xác nhận & ghép phụ đề".
  Có "Tìm & thay" (Enter / Shift+Enter nhảy câu sau / trước, "Thay tất cả", tích lưu vào Từ điển) và "Từ điển" (chữ gốc → dịch đúng; dịch sai → tự thay; áp cho cả Dịch phụ đề lẫn Dịch & Reup).
- Bước "Hậu kỳ & xác nhận" (Review/Reup): timeline cảnh; tab Cảnh (nghe cảnh, bỏ/dùng lại cảnh, chỉnh đoạn hình gốc, sửa lời đọc rồi "Tạo lại giọng"), Khung & sub (phụ đề, cắt khung, che mờ chữ cứng/logo, "Quét chữ Trung & xem trước"), Hiệu ứng, Âm thanh (tiếng gốc, nhạc nền, tự nén nhạc khi có lời), Kiểm tra (danh sách lỗi theo cảnh, bấm để mở cảnh), AI (AI rà & đề xuất sửa kịch bản, duyệt từng đề xuất).
  Nút "Tự hậu kỳ" = căn hình theo lời + AI sửa kịch bản + tạo lại giọng. Hoàn tác Ctrl+Z, làm lại Ctrl+Y. Phím: Space phát/dừng, ← → chuyển cảnh. Còn lỗi vẫn xuất được nhưng nên sửa trước. Bấm "Xuất video".
  Sửa lời mà chưa tạo lại giọng → báo đỏ; xác nhận xuất thì app tự đọc lại.
- Hoàn thành: "Mở video", "Hiện trong thư mục", "Kiểm tra chất lượng" (điểm /100, lỗi theo cảnh), "Bài đăng AI" (tiêu đề, mô tả, hashtag cho YouTube có mốc chương, Shorts, TikTok, Facebook, Instagram + 3 thumbnail; chọn giọng văn Hấp dẫn/Hài hước/Nghiêm túc/Cảm xúc; nút "Chép").
  Job đã xong còn có: "Mở lại hậu kỳ" (giữ giọng cũ hoặc đổi giọng, dừng ở bước Xem trước), "Lồng tiếng lại" (từ bản dịch đã có, không chạy lại Whisper/dịch), "Sửa phụ đề" (Dịch phụ đề: mở trình sửa ngay tại chỗ, bản sửa dở tự lưu — nút đổi thành "Sửa tiếp"; bấm "Dựng lại video" mới dựng).
- Lỗi / đã huỷ: "Tiếp tục từ “<bước>”" chạy tiếp từ bước hỏng (giữ các bước đã xong), "Chạy lại từ đầu" cùng cấu hình, "Dùng lại kịch bản" (Review/Reup, khi thư mục tạm đã bị dọn nhưng còn kịch bản); thông báo lỗi hiện ở cột phải, chi tiết trong Nhật ký.

## TIMELINE PHỤ ĐỀ (bước Sửa bản dịch của Dịch phụ đề)
3 làn: Gốc (sóng âm + phụ đề gốc, chỉ để so), Giọng (khung đọc lồng tiếng từng câu, có khi bật lồng tiếng), Phụ đề (từng dòng chữ Việt).
Vạch chuyển cảnh trên timeline; thanh trong khối giọng báo đọc vừa / nhanh / dài quá; viền vàng/đỏ = chữ chạy quá nhanh (ký tự/giây), có nút tự nới các dòng gấp.
Phím tắt:
- Kéo khối: dời phụ đề / giọng · Kéo mép: đổi lúc bắt đầu / kết thúc (màn hình hiện đúng khung hình ở mép đang kéo)
- Ctrl+B: tách dòng tại đầu phát · M: gộp dòng
- ← →: dời 0.1s (Shift: 1s)
- [ ]: đặt đầu / cuối = đầu phát
- S: bật/tắt hít (nam châm) · L: liên kết phụ đề & giọng cùng câu
- R: về giờ gốc
- ↑ ↓: dòng trước / sau · Space: phát / dừng
- Ctrl+Z / Ctrl+Y: hoàn tác / làm lại
- Ctrl + lăn chuột: zoom tại con trỏ
Khối không đè khối kề, không ra ngoài video. Giọng đọc đúng khung đã kéo, phụ đề hiện đúng giờ đã kéo khi xuất video.

## LỊCH SỬ
- Lọc: Tất cả / Đang chạy / Hoàn thành / Lỗi / huỷ; ô "Tìm theo tên video…"; "Làm mới".
- Mỗi dòng: mở thư mục, Tiếp tục (khi job lỗi có thể chạy tiếp từ bước dở), Chạy lại từ đầu với cấu hình cũ, Xoá. Bấm dòng để mở trong Studio.
- "Xoá tất cả" / "Xoá N job": xoá đúng các job đang hiện theo bộ lọc; job đang chạy/chờ giữ lại; video & file đã xuất giữ nguyên (chỉ dọn thư mục tạm, sau đó không Tiếp tục được).
- Job đang chạy không xoá được: mở job, bấm Dừng trước.

## PHỤ ĐỀ (trang riêng, 3 tab)
- Tách SRT: chọn video (file hoặc link), ngôn ngữ gốc, Whisper model, thiết bị; "Dịch sang tiếng Việt" (xuất thêm file _vi.srt, Google miễn phí hoặc "Dịch bằng AI"), bối cảnh phim, thư mục xuất.
- Ghép phụ đề: video gốc + file .srt có sẵn → chọn kiểu chữ (phong cách, bố cục dòng, cách đáy, màu chữ) → ghép vào video.
- Sửa SRT: mở file .srt, sửa chữ, chỉnh thời gian từng dòng (giờ:phút:giây,mili-giây), dời cả file "Sớm hơn" / "Muộn hơn", tìm trong phụ đề, xoá dòng, cảnh báo dòng chồng nhau / chữ chạy quá nhanh; "Lưu", "Ghép vào video".

## GIỌNG ĐỌC
- Trang Giọng đọc: lọc theo nhóm và giới tính, tìm giọng, nhập câu thử, "Tạo thử" từng giọng hoặc tạo thử hàng loạt, "Nghe lần lượt", "Đặt làm mặc định".
- Nhóm giọng:
  · CapCut (50 giọng, miễn phí, cần mạng; không cần đăng nhập — nếu CapCut bắt đăng nhập: Cài đặt → Giọng đọc → "Đăng nhập CapCut").
  · Edge TTS (Nữ Bắc, Nam Bắc — miễn phí, cần mạng).
  · VieNeu / VieNeu 3 (offline, miễn phí, chạy trên máy): cần tải model — thẻ "Giọng VieNeu (offline, miễn phí)" trên trang Giọng đọc → "Tải model VieNeu" (~1.2 GB, gỡ được).
  · Cao cấp FPT.AI (cần key FPT — Cài đặt → Giọng đọc → nhập key → "Lưu key"). Có ô key cho ElevenLabs / Viettel nếu dùng.
- VieNeu chỉnh được "Tốc độ (rate)" -30% … +50% (giữ cao độ) và "Cao độ (pitch)" -50 … +50 Hz (giữ tốc độ); ô số cạnh thanh trượt, ↑ ↓ tăng giảm, Enter để áp. Có ở tab giọng khi tạo video và bảng giọng từng nhân vật.
- Mọi ô chọn giọng có ô nhập câu thoại để nghe thử (Enter để đọc). Cả app chỉ phát 1 tiếng; nút đang phát đổi thành "Dừng".
- Chọn giọng nào đọc đúng giọng đó, không tự đổi sang giọng khác; câu lỗi được đọc lại bằng chính giọng đó.
- Gợi ý chọn giọng: muốn miễn phí, nhanh, nhiều sắc thái → CapCut; máy mạnh, muốn chạy offline, phân vai → VieNeu; giọng chuẩn tin tức cao cấp → FPT.AI (cần key).

## CÀI ĐẶT (5 tab)
- Tài khoản AI: đăng nhập ChatGPT / Gemini (xem trên).
- Giọng đọc: API key FPT.AI / ElevenLabs / Viettel (tuỳ chọn), "Đăng nhập CapCut" (không bắt buộc).
- Mặc định: Thư mục xuất, Whisper model, Thiết bị, Phong cách phụ đề, Bố cục dòng, Giọng đọc mặc định, "Chế độ nhẹ máy" (dùng ~nửa CPU, dựng 1 cảnh/lượt — bật khi cần dùng máy nặng song song). Bấm "Lưu".
- Giao diện: Sáng / Tối / Theo hệ thống, màu nhấn, cỡ giao diện.
- Hệ thống & cập nhật: kiểm tra / cài bản mới (tự cập nhật chỉ ở bản cài đặt), thông tin Python/GPU/ổ đĩa/ffmpeg, Giới thiệu (phiên bản, thư mục dữ liệu, "Mở log", lịch sử phiên bản).
- Dữ liệu người dùng nằm ở %APPDATA%\\ReviewFilm Studio\\ (không bị xoá khi cập nhật); log ở thư mục logs/ (main.log, backend.log).

## LỖI THƯỜNG GẶP & CÁCH XỬ LÝ
- Nút Bắt đầu bị khoá, khung "Cần kiểm tra" báo "Chế độ Review cần đăng nhập Gemini" → Cài đặt → Tài khoản AI → "Đăng nhập Google".
- "Chưa kết nối ChatGPT / Gemini" khi dùng Tự hậu kỳ / AI / Bài đăng → đăng nhập ở Cài đặt → Tài khoản AI, bấm "Kiểm tra" để chắc tài khoản hoạt động (badge "Lỗi" = phiên hết hạn → đăng nhập lại).
- "Hàng loạt cần từ 2 video trở lên" → 1 video thì dùng nguồn "File".
- "Chọn giọng cho nhân vật nữ" → tab Lồng tiếng, chọn giọng nữ hoặc tắt "Giọng riêng cho nhân vật nam / nữ".
- "Thiếu ffmpeg" → cài lại app / báo hỗ trợ.
- Whisper chậm hoặc lỗi GPU → máy không có GPU NVIDIA thì chọn Thiết bị = CPU, model base/small; hoặc dùng model "capcut" (online, nhanh).
- Edge TTS báo "No audio was received" / quá thời gian → thường do mạng chậm hoặc bị chặn tạm; chờ chút rồi bấm "Tiếp tục từ …" ở job lỗi, hoặc đổi sang giọng CapCut.
- Giọng VieNeu "Chưa dùng được trên máy này" → trang Giọng đọc → "Tải model VieNeu".
- Giọng FPT.AI mờ "cần key" → Cài đặt → Giọng đọc → nhập key → "Lưu key".
- Giọng CapCut lỗi hàng loạt → thử lại sau, hoặc Cài đặt → Giọng đọc → "Đăng nhập CapCut".
- Job lỗi giữa chừng → mở job trong Studio, xem Nhật ký; bấm "Tiếp tục từ …" để chạy tiếp từ bước hỏng (không làm lại từ đầu). Không có nút đó thì "Chạy lại từ đầu".
- Ổ đĩa sắp đầy (Tổng quan báo vàng) → dọn ổ hoặc đổi Thư mục xuất (Cài đặt → Mặc định).
- Lời đọc lệch hình / lặp hình (Review) → ở Hậu kỳ xem tab Kiểm tra, rút gọn lời hoặc bấm "Tự hậu kỳ"; bật "Phân tích chuyên sâu" cho lần sau.
- Còn sót chữ Trung / logo → tab Phụ đề: "Che phụ đề gốc / logo", kéo khung trùm kín; Dịch phụ đề chọn "Xoá sạch nét chữ"; hoặc bật "Tự che mọi chữ tiếng Trung"; hoặc dùng "Cắt khung hình".
- Tải video lỗi → bấm "Tải lại N lỗi"; link riêng tư / cần đăng nhập không tải được.
- Máy giật khi đang dựng → Cài đặt → Mặc định → bật "Chế độ nhẹ máy".
"""
