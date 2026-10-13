# ReviewFilm Studio

App desktop biến phim dài thành video review / dịch & reup có thuyết minh và phụ đề.
Electron + React (Vite, TS, shadcn/ui, Tailwind v4) + backend Python (FastAPI).

## Cấu trúc

```
reviewfilm/
├── electron/
│   ├── src/                 Electron main (TypeScript → electron/dist)
│   │   ├── main.ts          cửa sổ, IPC, vòng đời app
│   │   ├── paths.ts         đường dẫn dev ↔ bản cài đặt (một nơi duy nhất)
│   │   ├── backend.ts       chọn cổng, spawn/dừng backend Python
│   │   ├── python.ts        tìm Python, tạo venv, cài requirements (bản cài đặt)
│   │   ├── updater.ts       tự cập nhật qua GitHub Releases
│   │   ├── appInfo.ts       phiên bản, "Có gì mới" (đọc CHANGELOG.md)
│   │   ├── logger.ts        log ra file, xoay vòng
│   │   ├── auth.ts          license key
│   │   ├── usage.ts         CPU/RAM/GPU
│   │   └── preload.ts       cầu nối window.rf cho frontend
│   └── ai/                  tài khoản ChatGPT/Gemini web (ESM, lấy từ ToolYoutube)
├── frontend/src/
│   ├── pages/               Tổng quan, Tạo video, Studio, Phụ đề, Giọng đọc, Lịch sử, Cài đặt
│   ├── components/          component dùng chung (+ ui/ của shadcn)
│   ├── hooks/ lib/ app/     hook, API client, store, auth, theme
│   └── types/electron.d.ts  kiểu của window.rf
├── backend/
│   ├── main.py              entry: API (uvicorn) hoặc worker (--whisper/--xtts/--vieneu-worker)
│   ├── app/                 lớp API: config, constants, srt_utils
│   │   └── features/        jobs (hàng đợi + pipeline) · voices · settings · media
│   ├── core/                engine: Whisper, Vision AI, kịch bản, dịch, TTS, dựng video
│   ├── workers/             tiến trình TTS chạy riêng (XTTS, VieNeu)
│   ├── bin/                 ffmpeg, ffprobe
│   └── voice_samples/       giọng mẫu (thư mục con: vieneu/, vieneu3_ref/, xtts/…)
├── build/                   icon cho bộ cài
└── scripts/
    ├── electron.cjs         chạy Electron với env sạch
    └── version.cjs          tăng phiên bản + chốt CHANGELOG
```

## Chạy khi phát triển

```bash
pip install -r backend/requirements.txt      # hoặc tạo backend/.venv
npm install && npm --prefix frontend install
npm run dev        # Vite (hot reload) + Electron; Electron tự chạy backend
npm start          # dùng frontend đã build (npm run build)
```

Python khác: đặt `RF_PYTHON`, hoặc tạo `backend/.venv` (app tự dùng).
Khi dev, dữ liệu nằm trong `backend/data/` và key giọng đọc trong `backend/.env`.

## Dữ liệu người dùng (bản cài đặt)

Tất cả nằm trong `%APPDATA%\ReviewFilm Studio\`, **không bị xoá khi cập nhật**:

| Thư mục | Nội dung |
|---|---|
| `data/` | `settings.json`, `.env` (key giọng đọc), `jobs/`, cache nghe thử giọng |
| `python-env/` | venv Python của app (tự tạo lần đầu) |
| `ai/` | tài khoản ChatGPT/Gemini web + profile Chrome |
| `logs/` | `main.log` (Electron), `backend.log` (Python) — tự xoay vòng 5 MB × 3 |
| `state.json` | phiên bản lần chạy trước (để hiện "Có gì mới") |
| `auth.json` | license key |

## Tự cập nhật

- App kiểm tra bản mới trên GitHub Releases của `quochuy03/reviewfilm-public` khi mở và mỗi 4 giờ,
  tải nền, rồi báo "Khởi động lại & cập nhật" (thông báo + Cài đặt → Cập nhật).
- Bản mới đổi `backend/requirements.txt` → lần mở sau app tự `pip install` thêm (so bằng hash).
- Chỉ chạy ở bản cài đặt; bản dev hiện "Bản chạy từ mã nguồn".

## Phiên bản

[Semantic Versioning](https://semver.org/lang/vi/) — `MAJOR.MINOR.PATCH`:

| Lệnh | Khi nào | Ví dụ |
|---|---|---|
| `npm run version:patch` | chỉ sửa lỗi | `2.0.0` → `2.0.1` |
| `npm run version:minor` | thêm tính năng | `2.0.1` → `2.1.0` |
| `npm run version:major` | thay đổi lớn, phải cấu hình lại | `2.1.0` → `3.0.0` |

- `package.json` là **nguồn duy nhất** của số phiên bản: app (Cài đặt → Giới thiệu), backend (`/api/system`),
  bộ cài, tag GitHub đều lấy từ đây. Không sửa tay ở chỗ khác.
- Trong lúc làm, ghi thay đổi vào mục `## [Unreleased]` của `CHANGELOG.md` theo nhóm
  `### Added / Changed / Fixed / Removed`. Lệnh `version:*` chuyển mục đó thành `## [x.y.z] - ngày`
  (từ chối nếu mục trống) và cập nhật `package.json`, `package-lock.json`, `frontend/package.json`.
- Thử trước không ghi file: `node scripts/version.cjs minor --dry`.
- Người dùng thấy nội dung CHANGELOG của phiên bản mới trong hộp thoại "Có gì mới" sau khi cập nhật.

### Phát hành bản mới

1. Ghi thay đổi vào `[Unreleased]` → `npm run version:patch|minor|major`.
2. `npm run check` — kiểm tra TypeScript (Electron + frontend) và cú pháp Python.
3. Tạo GitHub token có quyền `repo`, đặt biến môi trường: `set GH_TOKEN=ghp_...`
4. `npm run release` → build + đóng gói NSIS + đẩy lên GitHub Releases (bản nháp, tag `vX.Y.Z`).
5. Vào GitHub → Releases → kiểm tra rồi **Publish**. Máy người dùng sẽ tự nhận bản mới.

Chỉ cần bộ cài để thử, không đăng: `npm run dist` → `release/ReviewFilm Studio Setup x.y.z.exe`.

## Ghi chú

- AI (Vision xem phim, viết kịch bản, dịch, phân vai) chạy bằng tài khoản ChatGPT/Gemini đăng nhập trong app
  (Cài đặt → Tài khoản AI) — không dùng API key OpenAI/DeepSeek/Gemini. Review bắt buộc đăng nhập Gemini.
  Dịch & Reup / Tách SRT không đăng nhập vẫn chạy (Google dịch miễn phí).
- API key chỉ còn cho giọng đọc cao cấp (FPT.AI, ElevenLabs, Viettel) — tuỳ chọn.
- Giọng VieNeu/XTTS cần Model Pack cài riêng; không có sẽ chuyển sang Edge TTS.
- Job chạy theo hàng đợi, mỗi lúc một job; job đang chờ sửa kịch bản/xem trước nhường lượt cho job sau.

## License key

- Xác thực qua `https://serverkey.taothaoai.com/api/review_film/auth` (`electron/src/auth.ts`).
- Backend chỉ khởi động sau khi key hợp lệ. Xác thực lại mỗi 30 phút; mất mạng dùng offline tối đa 3 ngày.
