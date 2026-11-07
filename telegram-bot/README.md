# Trợ lý Telegram cho ReviewFilm Studio

Nhắn 1 link + ý muốn cho bot → nó tự tải + dựng + lồng tiếng rồi gửi video về Telegram.
Bot gọi thẳng API của app (app phải đang mở), **không cần API key AI nào thêm**.

> Cách hoạt động: MCP không tự đẩy tin nhắn vào cho agent, nên con bot này đứng nghe
> Telegram (long-polling) và tự chạy job qua API `POST /api/jobs/video` — đúng kiểu "nhắn là nó làm".

## Cài 3 bước

1) **Tạo bot:** mở Telegram, nhắn **@BotFather** → `/newbot` → đặt tên → nó cho **token**
   (dạng `1234567:ABC...`).

2) **Cấu hình:**
   ```
   cd telegram-bot
   copy .env.example .env        (Windows)   |   cp .env.example .env   (Mac/Linux)
   ```
   Mở `.env`, dán `TELEGRAM_BOT_TOKEN`. Để trống `TELEGRAM_ALLOWED_IDS` lần đầu cũng được.

3) **Chạy** (mở sẵn ReviewFilm Studio trước):
   ```
   pip install -r requirements.txt
   python telegram_bot.py
   ```
   Nhắn bot 1 câu → nó in **ID Telegram** của bạn. Dán ID đó vào `TELEGRAM_ALLOWED_IDS`
   trong `.env` rồi chạy lại → từ đó chỉ mình bạn dùng được bot.

## Dùng

Gửi cho bot:
- `lồng tiếng <link>` — tải + lồng tiếng (chế độ Lồng tiếng)
- `reup <link>` — thuyết minh dịch từng câu
- `review <link>` — AI tóm tắt & làm video review
- `phụ đề <link>` — chỉ ghép phụ đề
- `tải <link>` — chỉ tải video
- Dán **link trơn** (không ghi gì) → chạy chế độ mặc định trong `.env` (`RF_TG_DEFAULT_MODE`)

Nguồn hỗ trợ: Douyin, TikTok, Bilibili, YouTube, Weibo, DramaBox… (như trong app).
Bot báo tiến độ ngay trong tin nhắn, xong gửi file video về. File quá ~50MB (giới hạn Telegram)
thì bot gửi **đường dẫn file trên máy** thay vì gửi trực tiếp.

## Lưu ý
- **App phải đang mở** (backend chạy cổng 47651) thì bot mới làm được.
- Luôn đặt `TELEGRAM_ALLOWED_IDS` — ai cũng có thể tìm ra bot, allowlist là tường bảo vệ thật.
- **Đừng commit file `.env`** (chứa token). Chỉ commit `.env.example`.
- Muốn "chat tự nhiên hơn" (bot tự hiểu câu dài, tự chọn giọng…): có thể nâng cấp sau bằng
  Claude Agent SDK nối vào **MCP sẵn có của app** — bản này cố tình giữ đơn giản & chắc chắn trước.
