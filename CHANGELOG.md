# Changelog

Mọi thay đổi đáng chú ý của ReviewFilm Studio được ghi ở đây.
Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/), phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/):

- **MAJOR** (`3.0.0`) — thay đổi lớn, có thể phải cấu hình lại.
- **MINOR** (`2.1.0`) — thêm tính năng, không phá vỡ cái cũ.
- **PATCH** (`2.0.1`) — sửa lỗi.

Ghi thay đổi vào mục **[Unreleased]** trong lúc làm. Khi phát hành: `npm run version:patch|minor|major`
sẽ chuyển mục đó thành phiên bản mới kèm ngày.

## [Unreleased]

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

[Unreleased]: https://github.com/quochuy03/reviewfilm-public/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/quochuy03/reviewfilm-public/releases/tag/v2.0.0
