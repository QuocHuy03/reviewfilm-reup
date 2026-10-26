# Changelog

Mọi thay đổi đáng chú ý của ReviewFilm Studio được ghi ở đây.
Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/), phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/):

- **MAJOR** (`3.0.0`) — thay đổi lớn, có thể phải cấu hình lại.
- **MINOR** (`2.1.0`) — thêm tính năng, không phá vỡ cái cũ.
- **PATCH** (`2.0.1`) — sửa lỗi.

Ghi thay đổi vào mục **[Unreleased]** trong lúc làm. Khi phát hành: `npm run version:patch|minor|major`
sẽ chuyển mục đó thành phiên bản mới kèm ngày.

## [Unreleased]

## [2.8.3] - 2026-10-26

### Added
- Timeline phụ đề: **số đếm nhanh** dưới tên mỗi làn (Gốc: dòng · cảnh; Giọng: câu · câu dài; Phụ đề: dòng · dòng gấp) và **thu gọn / mở rộng làn**
  khi bấm tên làn (nhớ lựa chọn).

## [2.8.2] - 2026-10-26

### Added
- Timeline phụ đề — nút ở đầu làn (icon thật, không emoji): **khoá làn** Giọng / Phụ đề (không kéo, cắt, sửa nhầm; vẫn bấm chọn & tua được),
  **loa** ở làn Gốc (tắt / bật tiếng gốc khi xem trước), **Kiểu chữ** ở làn Phụ đề (cỡ chữ, in hoa, song ngữ — xem trước ngay trên video,
  áp vào video khi Xác nhận / Dựng lại).

### Changed
- Trợ lý AI không dùng emoji (lời chào và câu trả lời đều chữ thuần, chuyên nghiệp).

## [2.8.1] - 2026-10-26

### Added
- Timeline phụ đề: **nút con mắt** ở làn Phụ đề (phím H) — ẩn phụ đề trên màn xem trước và khi dựng video thì **không ghép chữ Việt
  nhưng vẫn che phụ đề cũ** (file .srt vẫn xuất). Bật lại là có phụ đề như thường.

## [2.8.0] - 2026-10-26

### Added
- **Trợ lý AI** (khung chat nổi góc dưới phải + nút trên thanh tiêu đề): hỏi cách dùng app, nhờ giải thích lỗi job đang mở —
  trả lời từng bước, đúng tên nút. Gửi kèm **ảnh chụp màn hình** (Gemini đọc ảnh; dán bằng Ctrl+V / kéo thả) và **file chữ** (.srt, .log, .txt…).
  Dùng tài khoản ChatGPT / Gemini đã đăng nhập.
- **Thông báo khi job xong / lỗi / chờ duyệt**: thông báo trong app + thông báo Windows khi đang làm việc khác, bấm để mở job (tắt được trong Cài đặt).
- Dịch phụ đề: **phụ đề song ngữ** (dòng Việt + lời gốc nhỏ bên dưới, font chữ Trung / Hàn / Nhật đúng) và **xuất thêm bản dọc 9:16 / ngang 16:9
  cùng 1 lượt dựng** (nền mờ, video giữa, phụ đề to dưới video).
- Job Dịch phụ đề đã xong: menu **Xuất phụ đề** — song ngữ (.srt), WebVTT (.vtt), ASS (giữ kiểu chữ) — không dựng lại video.
- Timeline phụ đề đợt 2: **nghe thử giọng từng câu** ngay trên khối (V, ghi lại thời lượng đọc thật), **chọn nhiều khối** (Ctrl/Shift + bấm, Ctrl+A)
  để dời cả nhóm, **bấm đúp sửa chữ** trên khối, **phát lặp** khối đang chọn (P).

## [2.7.0] - 2026-10-26

### Added
- **Dịch phụ đề — timeline chỉnh tay** ở bước Sửa bản dịch: 3 làn **Gốc** (dòng phụ đề gốc để so) · **Lồng tiếng** (khung đọc từng câu) · **Phụ đề** (từng dòng chữ Việt).
  Kéo khối để dời, kéo mép để đổi lúc hiện / tắt (màn hình hiện đúng khung hình ở mép đang kéo); khối không đè khối kề, không ra ngoài video.
  **Hít** (S) vào đầu phát / mép khối khác / mép dòng gốc, **Liên kết** (L) phụ đề ↔ giọng cùng câu, ← → dời 0.1s (Shift 1s), `[` `]` đặt đầu / cuối = đầu phát,
  R về giờ gốc, Ctrl+Z / Ctrl+Y, zoom tại con trỏ, thanh tổng quan. Thanh trong khối giọng báo đọc vừa / nhanh / dài quá.
  Giọng đọc đúng khung đã kéo, phụ đề hiện đúng giờ đã kéo khi xuất video.
- Màn xem trước Dịch phụ đề hiện phụ đề **đúng từng dòng** như khi xuất (trước hiện cả câu).
- Timeline phụ đề: **sóng âm** video gốc (canh lúc bắt đầu / ngừng nói), **vạch chuyển cảnh** (hít vào để phụ đề không vắt qua 2 cảnh),
  **tách dòng** tại đầu phát (Ctrl+B) / **gộp dòng** (M), **cảnh báo tốc độ đọc** (ký tự/giây, viền vàng / đỏ) + nút **tự nới** các dòng gấp.
  Sóng âm & điểm cảnh tính 1 lần rồi lưu cache theo video.
- **Sửa phụ đề** ở job đã xong mở trình sửa ngay tại chỗ (không chạy lại pipeline); bấm **Dựng lại video** mới dựng. Bản đang sửa dở tự lưu — nút đổi thành "Sửa tiếp".

- Tải video: nút **Poster** trên thẻ xem trước (lưu ảnh bìa bản nét nhất vào `Downloads/Poster`); công tắc **Lưu poster** khi tải.
- Tải video: thư mục gọn kiểu Plex / Kodi — phim nhiều tập `Downloads/<Tên phim>/` (poster.jpg · Thông tin phim.txt · EP01.mp4…),
  video lẻ `Downloads/<Nền tảng>/` (kèm `<tên>-poster.jpg`). Danh sách đã tải gom tập theo phim (poster, số tập, dung lượng, **Làm cả bộ**).
- Tải video: **xem trước poster** (bấm ảnh bìa → phóng to bản nét, có nút Lưu poster), ô **Lưu vào** chọn thư mục ngay trên trang (nhớ lần trước),
  nút **Tải lại N lỗi** (chỉ tải lại mục lỗi), **tìm** phim / video đã tải, **ẩn** job khỏi danh sách và **Dọn** job đã xong (file giữ nguyên).

### Changed
- Chữ trên giao diện sửa bản dịch / timeline gọn hơn; bảng phím tắt dạng danh sách.
- Nút nhật ký ở Studio chuyển lên thanh tiêu đề (không còn nút tròn đè lên timeline).
- Poster tự lấy bản gốc nét nhất (bỏ tham số thu nhỏ của CDN, YouTube lấy maxres).

### Removed
- Tab **Link (URL)** ở Video nguồn của Tạo video (không dùng được) — tải phim ở trang Tải video rồi bấm tạo từ đó.

## [2.6.0] - 2026-10-24

### Added
- **Dịch phụ đề** có ở mọi lối vào tạo video: thẻ ở Trang chủ, nút "Dịch phụ đề" cạnh từng video đã tải (tự bật sẵn che phụ đề cũ).
- Trang Tải video: nút **Làm hàng loạt (N)** — tải xong cả lô phim, 1 bấm đưa hết sang Tạo video → Nhiều video, chọn mẫu kênh rồi chạy tự động lần lượt.
- Rate / pitch giọng VieNeu nhập được số trực tiếp (ô số cạnh thanh trượt, ↑ ↓ tăng giảm, Enter để áp).
- Giọng VieNeu chỉnh được **rate (%)** và **pitch (Hz, như Edge TTS)** — app đo cao độ thật từng câu rồi dời đúng số Hz; có ở tab Lồng tiếng và bảng giọng từng nhân vật (Tạo thử áp luôn rate / pitch).
- Ô **nhập câu thoại để nghe thử** cạnh nút "Tạo thử" ở mọi chỗ chọn giọng (Enter để đọc, nhớ câu đã gõ).
- Nút **Chỉnh thông số** trên thanh Studio: mở lại trang Tạo video với đúng video & thông số của job để sửa rồi chạy lại (hỏi dừng job cũ nếu đang chạy).
- Dịch phụ đề: 2 nút ngay ở phần Video nguồn — **Video gốc có phụ đề Trung** (có / không) và **Hiện phụ đề tiếng Việt trên video** (bật / tắt).
- Sửa bản dịch chuyên nghiệp ngay trong app: thanh **Tìm & thay** cho cả bản dịch (sửa 1 tên / cụm sai ở mọi câu một lần, Enter / Shift+Enter nhảy tới câu có chữ đó).
- **Từ điển dịch** của bạn (nút "Từ điển" ở bước sửa bản dịch): chữ gốc → AI luôn dịch đúng; cách dịch sai → tự thay sau khi dịch (cả Dịch phụ đề lẫn Dịch & Reup, cả dịch Google miễn phí). "Tìm & thay" tích "Lưu vào Từ điển" là lần sau tự sửa.
- Nút **Sửa phụ đề** ở job Dịch phụ đề đã xong: mở lại bước sửa bản dịch (giữ nguyên cấu hình, giọng, vai từng câu) rồi dựng lại video theo bản đã sửa — không nhận dạng / dịch lại từ đầu.
- Dịch phụ đề: phụ đề Việt hiện chồng lên video gốc theo đúng giây ở bước đang chạy và bước sửa bản dịch (sửa câu nào thấy ngay trên hình). Bản dịch hiện lên timeline ngay khi dịch xong — không phải chờ tới cuối job.

### Changed
- **Chạy nhẹ máy như app dựng video chuyên nghiệp:** mọi việc nặng (ffmpeg, Whisper, VieNeu, tách giọng, xoá chữ) chạy ưu tiên thấp và chia chung một ngân sách CPU theo số lõi (chừa lõi cho hệ thống) — trong lúc dựng, máy vẫn mượt như lúc rảnh (đo: độ trễ app khác 7ms thay vì 33ms, tệ nhất 12ms thay vì 192ms), tổng CPU ít hơn ~37%, thời gian dựng gần như không đổi.
- Cài đặt → **Chế độ nhẹ máy**: dùng khoảng nửa CPU, dựng 1 cảnh / lượt — khi cần dùng máy nặng song song.
- "Phân tích chuyên sâu" dò cắt cảnh nhanh hơn ~4× (ffmpeg giải mã đa luồng + thu nhỏ hình), cùng các điểm cắt.
- Cuối mỗi job ghi [HIỆU NĂNG]: thời gian, CPU máy trung bình / đỉnh — dễ biết job nào nặng.
- Dịch phụ đề: che phụ đề cũ mặc định **Nhanh** — che đúng khung chữ Trung từng câu, CHỈ lúc câu đó hiện, ngay trong lượt dựng (không còn lượt xoá chữ từng khung hình, không che cả dải suốt đoạn dài). "Xoá sạch nét chữ" (đẹp, chậm) vẫn chọn được ở tab Phụ đề.
- Che phụ đề cũ gom còn tối đa 4 vùng (trước tới 40 vùng, mỗi vùng thêm 1 lớp xử lý trên mọi khung hình) → dựng video nhanh hơn nhiều.
- Nghe thử giọng chuyên nghiệp hơn: cả app chỉ 1 tiếng phát — bấm nghe giọng khác thì giọng đang phát tự tắt; nút đang phát đổi thành **Dừng**; rời trang tự tắt tiếng.
- Lồng tiếng theo phụ đề cứng: các dòng liền nhau của cùng người nói được đọc liền 1 câu (tự nhiên, chia nhau thời gian) — phụ đề vẫn hiện đúng từng dòng.
- Câu khó vừa khung được đọc nhanh tới 1.3× (trước 1.2×) → ít phải nhờ AI rút gọn câu hơn.
- Tab Lồng tiếng gọn hơn: giọng nam / nữ đặt cạnh nhau, mô tả ngắn, tuỳ chọn ít dùng gom vào "Tuỳ chọn nâng cao".
- Chọn giọng nào đọc đúng giọng đó: không còn tự đổi sang Edge / Google / VieNeu khi giọng đã chọn lỗi (CapCut, VieNeu, FPT.AI, lồng tiếng theo vai). Câu lỗi được đọc lại bằng chính giọng đó; vẫn lỗi thì báo rõ câu nào. Bỏ tuỳ chọn "Giữ đúng giọng đã chọn" (giờ luôn bật).

- Dịch phụ đề: ô làm mờ chỗ phụ đề cũ / logo góc có mép mềm (mờ dần ra ngoài, vùng mờ nới rộng hơn vùng xoá chữ) — hết lộ ô chữ nhật cạnh sắc trên nền sáng.

### Fixed
- **Dịch & Reup bám miệng nhân vật:** hình luôn chạy tốc độ thật (trước tua nhanh tới 2.5× / chậm), lời dài thì mượn khoảng lặng tới câu sau → giọng nhanh nhẹ ≤1.35× → hình chậm nhẹ ≤1.25×; không gộp thoại thành khối 12s; không nhét câu "hook" vào câu thoại đầu; dịch AI có giới hạn số từ mỗi câu; câu quá dài AI tự rút gọn.
- Phụ đề SRT xuất kèm khớp video (đo độ dài clip thật, tính cả intro & tốc độ video); xem trước Hậu kỳ khớp video xuất (cùng cách chia đoạn phụ đề, cùng tốc độ hình / giọng).
- Review: hình không lấn sang cảnh sau (hết lặp hình); Vision AI chỉ xem phần hình sẽ chiếu; AI thiếu nhãn [Cảnh N] không còn chia đều lời (lệch hình); mô tả tự sinh ("Phan 3 trong 60") không bao giờ bị đọc thành lời.
- Mọi giọng đọc được cắt lặng đầu / cuối và cân âm lượng (≈ -17 LUFS) — lời vào đúng lúc, câu đọc lại không to nhỏ lệch nhau.
- Đọc số đúng: 2024 → "hai nghìn không trăm hai mươi tư", 50% → "năm mươi phần trăm", 10:30 → "mười giờ ba mươi", số điện thoại đọc từng số; phụ đề vẫn giữ chữ số.
- Sửa lời ở Hậu kỳ mà chưa tạo lại giọng → báo lỗi đỏ, xác nhận xuất thì tự đọc lại (không còn phụ đề mới – giọng cũ); "Tạo lại giọng" không gắn nhầm cảnh khi đổi thứ tự trong lúc chờ.
- VieNeu không còn dùng nhầm file giọng cũ / treo giữ GPU; phân vai không mất lời khi ghép lỗi; Edge ghi đúng lý do lỗi từng câu.
- Phụ đề không quá số dòng đã chọn; không hiện 2 đoạn cùng lúc ở khung ranh giới; SRT không còn mốc 00:00:60,000.
- Tự sửa / QA tìm đúng cảnh theo mốc thật; hoàn tác khôi phục đủ video + .srt / .ass / .vi.srt; QA báo cảnh bị bỏ khỏi video; QA đọc đúng fps.
- File TS/HLS tiếng bắt đầu muộn hơn hình: mốc câu nhận dạng không còn sớm hơn hình; Whisper dùng câu gợi ý đúng ngôn ngữ nguồn.
- Tải video: không treo khi yt-dlp báo nhiều lỗi; tải trực tiếp giữ đúng đuôi file, 2 lượt cùng tên không ghi đè nhau. Lưu nháp đến muộn sau khi xác nhận không tạo lại bản nháp cũ.
- Dịch phụ đề bằng Google (chưa đăng nhập AI): dịch đúng TỪNG DÒNG phụ đề gốc — câu Việt hiện đúng lúc câu Trung, không còn cắt ngang câu / lệch 1–2s; nhanh hơn ~10 lần.
- Logo góc bị sót khi bước quét gộp logo với chữ khác gần đó: tự tìm đúng phần đứng yên (logo thật) rồi xoá.
- Vùng che phụ đề cũ siết sát hàng chữ thật (đo trên video) — không còn vệt mờ lan lên người nhân vật.
- "Lồng tiếng lại": không còn lấy giọng app từng tự gán ở lần trước; 1 giọng thì mọi nhân vật đúng giọng đó; rate / pitch giữ đúng như lúc setup (nghe thử & lồng tiếng đều áp).
- Chọn 1 giọng thì mọi nhân vật đọc đúng giọng đó — không còn tự đổi nhân vật nam sang "Edge Nam Bắc" / nhân vật nữ sang "Edge Nữ Bắc". Chỉ chia giọng khi bật "Giọng riêng cho nhân vật nam / nữ" và chọn 2 giọng khác nhau.
- Lời lồng tiếng khác phụ đề: câu AI rút gọn lúc tạo giọng giờ cập nhật luôn phụ đề — chữ trên hình khớp đúng lời đọc.
- Giọng lồng tiếng bị mất âm cuối chữ khi tua nhanh / đổi cao độ (bộ co giãn nuốt phần cuối câu): đệm đuôi trước khi co giãn, giọng giữ trọn chữ và sạch, không rè.
- Giọng VieNeu chỉnh rate cao cộng dồn với tốc độ tua lồng tiếng gây nuốt chữ: tổng tốc độ giới hạn 1.35×.
- Bước sửa bản dịch / kịch bản giật lag với video dài (vài trăm câu): lúc chờ sửa, backend gửi lại toàn bộ danh sách câu mỗi 0.4 giây (đồng hồ job đổi → coi như "có thay đổi"), giờ chỉ gửi khi câu thật sự đổi. Gõ 1 câu / phát video không còn vẽ lại cả danh sách và cả nghìn khối trên timeline — chỉ dòng vừa sửa và đầu phát.
- Edge TTS báo "No audio was received" / quá thời gian hàng loạt câu khi mạng chậm: chờ kết nối 40s (trước 10s).
- Dựng video kẹt mãi ở 65% (Dịch phụ đề có nhiều vùng che phụ đề cũ / logo, Review có nhiều vùng chữ tự che): mỗi vùng 1 cặp split → overlay nối tiếp làm thời gian dựng tăng gấp đôi theo từng vùng (22 vùng đã không xong). Giờ tách luồng 1 lần cho mọi vùng, làm mờ chỉ lúc vùng cần che — 40 vùng dựng 10s video trong ~25s.

## [2.5.0] - 2026-10-23

### Added
- 41 giọng tiếng Việt mới của CapCut (tổng 50 giọng: người kể chuyện, chàng trai / cô gái nhiều sắc thái, giọng ElevenLabs Sài Nữ / Hà Nữ / Duy Bắc / Nam Trầm…), có sẵn file nghe thử. Không cần cookie; nhóm giọng mà API web từ chối tự đi qua API bản PC của CapCut.
- Tải phim ngắn (DramaBox, GoodShort, ShortMax, NetShort, FreeReels, Hồng Quả, KissKH…): 1 link = cả bộ phim, chọn tập bằng `#ep=1-10,15`, tải 3 tập song song, kèm phụ đề nếu nền tảng có.
- Tải video xong tạo luôn phụ đề tiếng gốc + bản dịch Việt bằng CapCut (chọn ngôn ngữ gốc ở trang Tải video).

### Changed
- Dịch phụ đề: SRT gốc đọc từ phụ đề trên hình được làm sạch trước khi phân vai / dịch (gộp dòng đọc lỗi lúc chữ mờ dần); mỗi dòng phụ đề gốc = 1 câu lồng tiếng, phụ đề Việt hiện / tắt đúng giờ dòng Trung.
- Che phụ đề cũ: xoá sạch nét chữ Trung (phụ đề + chữ / logo 4 góc), lấp thêm đúng khung từng câu lúc câu hiện — hết vệt chữ sót trên nền sáng.
- Tốc độ đọc lồng tiếng theo từng đoạn hội thoại (ngắt ở khoảng lặng ≥ 1.5s): mỗi đoạn chọn tốc độ thấp nhất (1.00–1.20×) mà giọng không trễ quá 0.25s, cùng 1 nhịp trong đoạn — phim dài không còn trễ dồn (bản cả phim chung 1 tốc độ trễ tới ~4.5s).
- Đã làm mờ dải phụ đề cũ thì phụ đề Việt chỉ chữ trắng viền đen, không ô nền đen (hết mảng xám xịt).

### Fixed
- Logo góc bị bỏ sót khi có nhiều vùng chữ cùng góc: chỉ gộp các mảnh chạm / sát nhau, cụm quá to thì giữ từng mảnh nhỏ.
- Edge TTS bị chặn tạm hàng loạt câu: gửi 8 câu / lượt (thay vì 30), thử lại 4 lần, chờ tăng dần; lỗi lẻ 1–2 câu chỉ đọc riêng câu đó bằng giọng dự phòng (không đổi giọng cả nhân vật).

## [2.4.7] - 2026-10-22

### Added
- Dịch phụ đề xuất được khung dọc 9:16 (Shorts / TikTok) — chọn ở tab Quy trình; video ngang nằm giữa, trên / dưới viền đen; cỡ chữ phụ đề tính theo bề ngang (không to tràn 3 dòng).

### Changed
- Logo / chữ đứng yên ở 4 góc được XOÁ (lấp bằng điểm ảnh xung quanh, mịn viền) thay vì làm mờ thành ô chữ nhật lộ; dải phụ đề vẫn làm mờ như Review.

### Fixed
- Câu AI dịch sót được dịch bổ sung từng câu một (trước gộp nhiều câu thành 1 khối → lệch câu, có câu giọng Việt đọc chữ Trung).
- Tách giọng chạy nền tự dừng khi job lỗi / xong (không chạy tiếp tốn CPU, giữ file trong thư mục tạm).
- "Lồng tiếng lại": dữ liệu phân vai luôn khớp số câu (trước có thể mất câu cuối / gán lệch vai); bước duyệt luôn hiện vai & chọn giọng.
- Đọc phụ đề cứng: ffmpeg dừng giữa chừng thì bỏ kết quả (không lưu cache nửa phim).
- VieNeu nhiều giọng: đọc số bằng chữ như đường đọc thường (trước đọc sai chữ số, dễ lỗi phải đổi giọng).

## [2.4.6] - 2026-10-22

### Fixed
- Dải che phụ đề của Dịch phụ đề rộng như Review phim (dải giữa ≥ 80% chiều ngang): phụ đề Việt dài hơn chữ Trung không còn lòi ra 2 bên dải mờ.
- Không còn che lố cả video: dải phụ đề AI tự căn tối đa 22% chiều cao; logo góc chỉ nhận vùng nhỏ (≤ 30% ngang, ≤ 18% cao), gộp 1 vùng / góc; không thấy phụ đề cứng thì không che dải (chỉ che logo góc nếu có).

## [2.4.5] - 2026-10-22

### Added
- Lịch sử: nút "Xoá tất cả" — xoá đúng các job đang hiện theo bộ lọc / ô tìm (chọn "Lỗi / huỷ" thì chỉ xoá job lỗi); job đang chạy / chờ tự giữ lại; dọn thư mục tạm, video & file đã xuất giữ nguyên.

### Changed
- "Lồng tiếng lại": luôn phân tích nhân vật TRƯỚC rồi dừng ở bước "Duyệt kịch bản theo vai" (kiểm tra ai nói câu nào, chọn giọng từng nhân vật) mới tạo giọng — kể cả job cũ chưa có phân vai; dòng không rõ nhân vật vẫn lồng tiếng (vai "Người dẫn").
- Hộp thoại "Lồng tiếng lại" rộng hơn: giọng nam / nữ 2 bên, danh sách nhân vật 2 cột, ghi rõ các bước.

### Fixed
- Dịch phụ đề: timeline & danh sách câu (bước duyệt, màn Hoàn thành) đặt mỗi câu đúng thời điểm thật trong video thay vì xếp nối nhau từ 0s như Review — trước đây nhìn như giọng / phụ đề lệch miệng nhân vật, bấm câu nhảy sai chỗ.

## [2.4.4] - 2026-10-22

### Changed
- Dịch phụ đề (có / không lồng tiếng) che phụ đề cũ y hệt Review phim, 1 kiểu duy nhất: làm mờ cố định cả dải phụ đề + logo 4 góc suốt video (bỏ lựa chọn "Xoá nhẹ" / "Xoá sạch nét chữ" / "Vừa theo chữ" ở chế độ này) — ổn định, nhanh, nhẹ RAM.

## [2.4.3] - 2026-10-22

### Fixed
- Phim dài lỗi ở bước dựng video "ffmpeg … Error initializing filters | Cannot allocate memory": biểu thức bật/tắt vùng che theo thời gian (hàng trăm câu phụ đề) quá dài → gộp các khoảng sát nhau còn tối đa 50 khoảng (không bỏ khoảng nào, vẫn che đủ). Trước đây chỗ che chữ tự động còn cắt bớt khoảng → cuối phim có thể lộ chữ.

## [2.4.2] - 2026-10-21

### Changed
- Lồng tiếng mặc định nam 1 giọng, nữ 1 giọng: bật sẵn "Giọng theo nhân vật nam / nữ" (giọng nữ mặc định Edge Nữ Bắc); "giọng nam" lỡ là giọng nữ thì tự dùng Edge Nam Bắc cho nhân vật nam (có cảnh báo ở tab Lồng tiếng) — mọi nhân vật nam cùng 1 giọng, mọi nhân vật nữ cùng 1 giọng, trừ khi tự đổi ở bước duyệt.

## [2.4.1] - 2026-10-21

### Fixed
- Giọng lồng tiếng cố định, không "nhảy": cả video đọc cùng 1 tốc độ (tính 1 lần, 1.0–1.2×) thay vì mỗi câu một tốc độ; nhân vật phải đổi sang giọng dự phòng (Edge / VieNeu lỗi) thì đổi cho MỌI câu của nhân vật đó — không còn câu giọng này câu giọng kia.

## [2.4.0] - 2026-10-21

### Added
- Dịch phụ đề: kiểu che "Xoá sạch nét chữ" (mặc định) — mặt nạ đúng nét chữ Trung từng khung (lọc theo hình dạng nét: bỏ vật sáng ở nền như vỏ dưa, mảng sáng), lấp ưu tiên bằng hình thật ở khung lân cận (căn độ dịch, kiểm từng điểm), còn lại lấp từ xung quanh; gộp watermark nhiều dòng. Chạy song song nhiều nhân CPU (~1.5–2 phút xử lý / 1 phút video): không khung mờ, không vệt, giữ chi tiết nền.
- Căn thời gian lồng tiếng theo VideoLingo: mỗi câu được mượn tối đa 1.5s khoảng lặng phía sau; dài hơn khung thì đọc nhanh nhẹ tối đa 1.2× (giữ cao độ giọng); tua tối đa vẫn không vừa mới nhờ AI viết gọn (giữ nghĩa bản dịch nhiều nhất); câu ngắn < 2.5s của cùng người gộp với câu sau. Không bao giờ chồng tiếng, không tua chậm.
- Lấy phụ đề cứng làm lời gốc (mặc định bật): video có phụ đề Trung in sẵn thì đọc thẳng phụ đề trên hình (5 khung/giây, chỉ OCR khi dải phụ đề đổi câu, nhận nét chữ trắng viền đen) → đúng chữ (không nghe nhầm như Whisper) và đúng lúc từng câu hiện / tắt; dịch & lồng tiếng đúng lúc phụ đề gốc hiện. Không có phụ đề cứng thì tự dùng Whisper.
- Chỉ lồng tiếng câu có phụ đề Trung trên hình (mặc định bật): quét phụ đề cứng ngay từ đầu (dùng chung cache với bước che chữ) — câu nhân vật nói có phụ đề mới đọc, tiếng đám đông / lời nền / nhạc giữ tiếng gốc; video không có phụ đề cứng (hoặc < 30% câu có phụ đề) thì lồng mọi câu thoại.
- Duyệt kịch bản theo vai trước khi tạo giọng: bước "Sửa bản dịch" của lồng tiếng hiện từng câu lồng tiếng (đúng thời gian nói) kèm ô chọn nhân vật (hoặc "Không lồng tiếng"), lời gốc và lời Việt — sửa vai / lời xong mới đọc.
- Ước lượng độ dài trước khi tạo giọng (như VideoLingo): câu dịch dài quá khung kể cả khi đọc nhanh 1.2× được AI viết gọn ngay sau khi dịch, đỡ phải tạo giọng → rút gọn → tạo lại.
- AI dịch 2 lượt như biên dịch chuyên nghiệp: dịch sát nghĩa → tự soát nghĩa / xưng hô / độ tự nhiên → câu lồng tiếng cuối.
- Sửa lỗi "Phân tích ngữ cảnh lỗi" khi dịch (AI viết thêm câu dẫn ngoài khối JSON) — bản dịch giữ được tên nhân vật / bối cảnh phim.
- Giọng theo nhân vật: phân tích trước cả video — nhận ra từng nhân vật bằng "dấu vân giọng" (model CAM++ tiếng Trung, ~27MB, tải 1 lần), giới tính theo cả nhân vật; câu ngắn gán về nhân vật cùng giới gần nhất (không gán nhầm nam ↔ nữ); tối đa 6 nhân vật chính + nam phụ / nữ phụ.
- Watermark / logo cố định: tự học mẫu nét chữ từ ~40 khung rải cả video rồi xoá theo mẫu ở mọi khung — cảnh nền sáng (chữ trắng trên trời trắng) vẫn xoá sạch; vùng logo không còn bị xoá cả khung chữ nhật.
- Kiểu che "Xoá nhẹ (tự nhiên)" (mặc định): lấp chỗ chữ cũ / logo bằng hình xung quanh như xoá logo, mượt viền — gần như không thấy vết; "Làm mờ" vẫn chọn được.
- Chỉ che khi có chữ: AI quét trước, video không có phụ đề cứng thì không che; có thì chỉ che lúc phụ đề cũ hiện.
- "AI tự căn vùng che": AI xem các khung hình, tìm đúng chỗ phụ đề cũ (cao, thấp, rộng) và đặt vùng che trùm kín — nút trong khung chỉnh vùng che; ở chế độ Dịch phụ đề tự làm lúc dựng (quét cả phim).
- Dịch phụ đề: nút "Lồng tiếng" cho video đã xong — lồng tiếng từ bản dịch có sẵn, không chạy lại Whisper / dịch.
- Quy trình lồng tiếng mới: phân tích nhân vật trên SRT gốc TRƯỚC (nghe giọng + AI đọc lời gốc: ai nói câu nào, nam / nữ, tên vai) → gộp mẩu câu Whisper cắt vụn của cùng người nói → AI dịch theo vai (đúng xưng hô từng cặp nhân vật, mỗi câu có số từ tối đa theo thời gian câu gốc) → đọc đúng lúc nhân vật nói thật (không còn giọng chạy trước hình).
- Tự chọn giọng từng nhân vật: bước "Duyệt kịch bản theo vai" có bảng "Giọng từng nhân vật" (tên, nam / nữ, số câu, nghe thử) — mặc định nam đọc giọng nam, nữ đọc giọng nữ đã chọn, tool không tự gán giọng khác; "Lồng tiếng lại" cũng đổi giọng từng người được, giữ nguyên phân vai.
- Tách lượt lời khi 2 nhân vật đối đáp nhanh: Whisper lấy thời gian từng chữ; đoạn Whisper gộp lời 2 người (không dấu câu, không ngừng) được tách đúng chỗ đổi giọng bằng "dấu vân giọng" (khác người ~0.2, cùng người ~0.6) — bám dấu câu / khoảng ngừng, không cắt giữa từ.
- Bảng dịch chung cho cả phim: AI đọc toàn bộ kịch bản gốc trước → tóm tắt, tên riêng / thuật ngữ (Hán Việt) và xưng hô từng cặp nhân vật, dùng cho mọi câu dịch.
- Dịch phụ đề che phụ đề cũ y như Review phim (mặc định "Làm mờ (như Review)"): làm mờ cố định cả dải phụ đề suốt video + tự làm mờ chữ / logo đứng yên ở 4 góc; "Xoá nhẹ" / "Xoá sạch nét chữ" vẫn chọn được.
- Lồng tiếng: tách giọng gốc khỏi nhạc nền (UVR MDX-Net ~64MB, chạy nền song song từ đầu job) — lúc giọng Việt đọc thì tắt hẳn giọng Trung, nhạc nền & tiếng động giữ nguyên; công tắc "Tách giọng gốc, giữ nhạc nền" (mặc định bật).
- Chỉ lồng tiếng lời thoại nhân vật: lời bài hát, tiếng động, tiếng cười / hét, chữ quảng cáo… không đọc, giữ nguyên tiếng gốc.
- VieNeu đọc nhiều nhân vật trong 1 lần nạp model (trước nạp lại ~13 giây cho mỗi giọng); câu VieNeu lỗi tự đọc bằng Edge đúng giới tính, câu Edge lỗi (bị chặn tạm "No audio was received") tự đọc bằng VieNeu offline đúng giới tính — không còn câu bị trống tiếng.

### Fixed
- "Xoá sạch nét chữ" chỉ xoá phụ đề cũ + chữ / logo ở 4 góc (watermark kênh, "nội dung hư cấu"…), không xoá chữ trong cảnh (biển hiệu, màn hình điện thoại…) — trừ khi bật "Tự che mọi chữ tiếng Trung".
- Phim dài không còn làm sập app khi máy thiếu RAM: bước "Xoá sạch nét chữ" tự bớt luồng theo RAM trống (~0.35GB / luồng ở 1080p); kết quả đọc phụ đề cứng được lưu cache → chạy lại không phải đọc lại cả phim.
- Giọng lồng tiếng bị trễ dồn: cắt khoảng lặng thừa Edge chèn đầu / cuối mỗi câu (~0.25s + ~1s) trước khi xếp lịch — trễ nhất từ ~9s còn ~1s.
- AI phân vai / rút gọn bị bỏ qua khi ChatGPT bọc kết quả trong thẻ `<CodeBlock …>` / `<escape>`.
- Câu Edge TTS lỗi lẻ tẻ không còn bị bỏ trống tiếng — tự đọc lại.

### Changed
- Dịch phụ đề: lồng tiếng mặc định BẬT, công tắc nằm ngay ở thẻ Video nguồn.
- Kiểu khung mờ mặc định "Cả dải (như CapCut)" — một dải mờ cố định, phụ đề Việt nằm giữa; "Vừa theo chữ" vẫn chọn được.

## [2.3.0] - 2026-10-19

### Added
- Lồng tiếng theo nhân vật nam / nữ: tự nhận câu giọng nữ trong video gốc (theo cao độ giọng) và đọc bằng giọng nữ đã chọn.
- Bước sửa bản dịch (khi lồng tiếng): mỗi câu hiện thời gian có / cần để đọc — vàng: sẽ đọc nhanh hơn, đỏ: dài quá, AI sẽ rút gọn.
- Dịch phụ đề: tab "Lồng tiếng" — đọc tiếng Việt đúng lúc từng câu thoại gốc, giữ nguyên thời gian video (không kéo giãn hình). Câu dài: đọc nhanh hơn chút (≤1.3×), vẫn dài thì AI rút gọn; không chồng tiếng. Tiếng gốc tự hạ nhỏ (mức chỉnh được) khi có lời Việt, giữ nguyên nhạc & hiệu ứng.
- Dịch phụ đề: "Khung mờ vừa theo chữ" (mặc định) — bề ngang khung mờ co giãn theo từng câu tiếng Việt, tự nới cho trùm hết chữ phụ đề cũ hiện cùng lúc (AI đo), không che thừa cả dải.
- Chế độ mới "Dịch phụ đề" ở trang Tạo video: Whisper → dịch tiếng Việt → che phụ đề cũ (vùng che / AI quét chữ Trung) → ghép phụ đề Việt nằm giữa vùng che, giữ nguyên tiếng gốc (không lồng tiếng). Xuất video + SRT gốc + SRT tiếng Việt; có bước sửa bản dịch trước khi ghép.
- Trang Giọng đọc: "Tạo thử tất cả" (đọc câu thử bằng mọi giọng đang hiện) và "Nghe lần lượt" (phát lần lượt từng giọng để chọn nhanh).
- "Phụ đề mới nằm giữa vùng che" (mặc định bật khi che phụ đề gốc): chữ tiếng Việt căn đúng tâm vùng che phụ đề cũ — kéo vùng che tới đâu phụ đề theo tới đó, 1 hay 2 dòng đều giữa. Đồng bộ ở trang Tạo video và Hậu kỳ.
- Độ dài review "Tự động theo video" (mặc định): phim ngắn kể gần hết, phim dài tóm gọn (phim 20′ → ~8′, 90′ → ~13′, 2 giờ → ~16′). Vẫn chọn được Ngắn / Vừa / Dài / Tuỳ chỉnh.
- Hậu kỳ → Khung & sub: "Quét chữ Trung & xem trước" — AI tìm chữ Trung theo từng cảnh, hiện mờ ngay trên màn xem trước đúng lúc chữ xuất hiện. Tắt / xoá / kéo sửa từng vùng theo cảnh, thêm vùng tay cho cảnh đang xem, tắt một vùng ở mọi cảnh một lần (vd logo muốn giữ). Xuất video dùng đúng danh sách đã sửa.

## [2.2.2] - 2026-10-19

### Added
- Nút "Hỗ trợ & liên hệ" (taothaoai.com) ở thanh bên, mục Giới thiệu trong Cài đặt và màn hình lỗi khởi động.

### Changed
- Thanh bên hiện icon kèm tên mục bên dưới — dễ nhìn, dễ tìm hơn.

## [2.2.1] - 2026-10-19

### Added
- Nút "Tải model VieNeu" ở trang Giọng đọc: cài giọng VieNeu offline ngay trong app (~1.2 GB, một lần), có tiến trình, huỷ, gỡ. 25 giọng có sẵn mới + 28 giọng VieNeu3, chạy CPU, không cần card màn hình.
- Màn chờ khởi động có nút "Thử lại" và "Mở log" khi chuẩn bị môi trường lỗi.

### Fixed
- Máy chưa cài Python không mở được app — app tự tải Python 3.12 bản portable (không cần quyền admin). Máy có Python quá mới (3.13/3.14) cũng dùng bản này cho ổn định.
- Máy thiếu Microsoft Visual C++ Runtime bị lỗi "DLL load failed" khi chạy Whisper / quét chữ — app tự tải bộ cài của Microsoft.
- Thư viện cài xong được kiểm tra chạy thật; gói nào lỗi thì tự cài lại gói đó. Môi trường Python hỏng (đã gỡ Python gốc) tự tạo lại.
- Giọng VieNeu không chạy được trên mọi máy (đường dẫn cố định của máy khác). Giọng cũ không còn trong model mới (Bình An, Gia Bảo, Ngọc Lan, Trọng Hữu) tự đọc bằng giọng gần nhất.
- Model Whisper được tải sẵn ngầm khi mở app — job đầu tiên không phải chờ tải.

## [2.2.0] - 2026-10-17

### Added
- Tự che mọi chữ tiếng Trung (AI quét): tìm chữ Trung ở bất kỳ đâu trên hình (phụ đề cứng, dải tiêu đề, logo chữ, chữ chèn) và làm mờ đúng chỗ, đúng lúc chữ hiện. Chọn độ kỹ (1 / 2 giây) và độ mờ; có ở trang Tạo video và tab "Khung & sub" của Hậu kỳ. Kết quả quét được lưu — dựng lại không phải quét lại.

## [2.1.1] - 2026-10-17

### Fixed
- Máy cài mới bị lỗi Whisper ngay bước nhận dạng giọng nói ("unexpected keyword argument 'metadata_errors'") do thư viện PyAV bản mới — app tự đọc audio, không còn phụ thuộc phiên bản PyAV.

## [2.1.0] - 2026-10-17

### Added
- Hiệu ứng & chuyển cảnh: 12 kiểu chuyển cảnh (mờ dần, trượt, quét, phóng to, ngẫu nhiên…), màu phim, zoom chậm, tối viền — độ dài video giữ nguyên, lời và phụ đề không lệch.
- Cắt khung video gốc (khung 8 tay cầm, phủ kín hoặc giữ trọn) ngay ở trang Tạo video và ở bước Hậu kỳ — bỏ hẳn dải phụ đề cứng / logo / tiêu đề.
- Bước Hậu kỳ: tab "Khung & sub" (che mờ, cắt khung, bật/tắt phụ đề, đặt phụ đề đè đúng chỗ chữ cũ) và tab "Hiệu ứng".
- 4 font có sẵn đủ dấu tiếng Việt (Baloo 2, Be Vietnam Pro, Montserrat, Oswald), phong cách "Game vàng in hoa", tuỳ chọn nền mờ sau chữ và màu viền.
- Timeline: thanh tổng quan, lăn chuột cuộn ngang, nút dời cảnh, hoàn tác / làm lại.
- "Dùng lại kịch bản" cho job lỗi mất thư mục tạm — bỏ qua Whisper & bước viết kịch bản.

### Changed
- Tạo giọng CapCut gom gói chạy song song (90 cảnh ~6 phút thay vì ~20 phút); tự hậu kỳ tạo lại giọng một lượt (~3 phút thay vì ~87 phút).
- Whisper trên CPU dùng chế độ nhanh; hiện thời gian ước tính khi chọn model.
- Kịch bản chia số từ theo độ dài hình từng cảnh — tự hậu kỳ ít phải viết lại.
- Giao diện gọn hơn: trang Tạo video, Phụ đề (Tách / Ghép / Sửa SRT), Cài đặt dùng chung bố cục; app mở nhanh hơn.

### Removed
- Engine giọng không dùng (clone giọng, OpenAI, ElevenLabs, Viettel) và ô nhập key tương ứng.

### Fixed
- Video Dịch & Reup bị mất hình (đứng hình) sau khoảng phút 1 khi có chuyển cảnh và nhiều cảnh.
- Dịch miễn phí bằng Google trả nguyên văn (không dịch).
- 23 giọng VieNeu3 đọc nhầm thành "Bình An"; giọng tạo lại bị lẫn khi CapCut lỗi chuyển sang Edge.
- QA không phát hiện video mất hình; báo sai độ dài với Dịch & Reup.
- Thông báo lỗi tải video dễ hiểu hơn (TikTok chặn khu vực, máy chủ lỗi).

## [2.0.0] - 2026-10-13

### Added
- Tự cập nhật qua GitHub Releases: kiểm tra khi mở app và mỗi 4 giờ, tải nền, bấm "Khởi động lại" để cài.
- Môi trường Python tự tạo ở lần chạy đầu; bản mới đổi thư viện thì tự cài thêm.
- Hàng đợi job: tạo nhiều job liền, chạy lần lượt; job đang chờ sửa kịch bản nhường lượt và được ưu tiên khi tiếp tục.
- Chạy lại job trong Lịch sử với đúng cấu hình cũ.
- Tài khoản ChatGPT / Gemini web (Cài đặt → Tài khoản AI) cho Vision, viết kịch bản, dịch, phân vai.
- Review chạy được với video không có lời thoại (AI viết kịch bản từ hình ảnh).
- Hộp thoại "Có gì mới" sau khi cập nhật; mục Giới thiệu (phiên bản, thư mục dữ liệu, log).
- File log trong `%APPDATA%\ReviewFilm Studio\logs` (tự xoay vòng).

### Changed
- Dữ liệu người dùng (cài đặt, key, lịch sử job) chuyển sang `%APPDATA%` — giữ nguyên khi cập nhật.
- Cấu trúc lại mã nguồn: Electron tách module, pipeline chia bước, worker TTS vào `backend/workers/`.
- Thư mục giọng mẫu đổi tên `voice_samples/`.

### Removed
- API key OpenAI / DeepSeek / Gemini — AI chạy hoàn toàn bằng tài khoản web.
- Module cũ không dùng của bản PyQt (chuyển vào `_legacy/`).

### Fixed
- Giọng tham chiếu VieNeu 3 không tìm thấy file mẫu.
- Không tạo được job mới khi đang có job chạy (lỗi 409).

[Unreleased]: https://github.com/quochuy03/reviewfilm-public/compare/v2.8.3...HEAD
[2.8.3]: https://github.com/quochuy03/reviewfilm-public/compare/v2.8.2...v2.8.3
[2.8.2]: https://github.com/quochuy03/reviewfilm-public/compare/v2.8.1...v2.8.2
[2.8.1]: https://github.com/quochuy03/reviewfilm-public/compare/v2.8.0...v2.8.1
[2.8.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.7...v2.5.0
[2.4.7]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.6...v2.4.7
[2.4.6]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.5...v2.4.6
[2.4.5]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.4...v2.4.5
[2.4.4]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.3...v2.4.4
[2.4.3]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.2...v2.4.3
[2.4.2]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.1...v2.4.2
[2.4.1]: https://github.com/quochuy03/reviewfilm-public/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.2.2...v2.3.0
[2.2.2]: https://github.com/quochuy03/reviewfilm-public/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/quochuy03/reviewfilm-public/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.1.1...v2.2.0
[2.1.1]: https://github.com/quochuy03/reviewfilm-public/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/quochuy03/reviewfilm-public/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/quochuy03/reviewfilm-public/releases/tag/v2.0.0
