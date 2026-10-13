"""
VieNeu-TTS worker — standalone executable, no Python needed on customer machine.
Built with PyInstaller (Python 3.14) and bundled inside Model Pack.

Usage:
    vieneu_worker.exe <batch_json> <voice_id> [ref_audio_path] [hf_home]

batch_json:     JSON list[{"text": "...", "out": "path.wav"}]
voice_id:       binh-an | xuan-vinh | ngoc-lan | ... | clone
ref_audio_path: (optional) path to reference audio for voice cloning
hf_home:        (optional) HuggingFace cache dir (models/vieneu/hub inside Model Pack)
"""
import sys
import json
import os

# QUAN TRONG: phai set TRUOC bat ky import nao lien quan huggingface_hub/vieneu.
# Neu thieu se crash "memory allocation failed" khi tai model lan dau tren
# Windows qua hf-xet (transfer backend moi cua huggingface_hub) — loi da biet
# truoc, khong phai doi gap loi moi tin.
os.environ["HF_HUB_DISABLE_XET"] = "1"

# KHONG set PYTORCH_CUDA_ALLOC_CONF — option nay khong duoc mot so ban torch ho tro
# (xem giai thich chi tiet trong main.py/xtts_worker.py). Vo hai o day vi device da bi
# ep "cpu" ben duoi, nhung bo di cho sach, tranh sao chep lai pattern da biet co van de.

# Console mac dinh tren mot so may Windows dung codepage ANSI (cp1252/cp1258...)
# khong encode duoc dau tieng Viet -> print() crash UnicodeEncodeError, lam worker
# chet ngang khi dang tao giong cho khach. Ep stdout/stderr ve UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _patch_torchaudio_load():
    """torchaudio mới yêu cầu package torchcodec để load audio, nhưng
    Model Pack không bundle torchcodec (cần FFmpeg link riêng, dễ vỡ khi
    đóng gói PyInstaller). Fallback sang soundfile (đã có sẵn) khi
    torchaudio.load lỗi thiếu torchcodec."""
    try:
        import torchaudio
    except ImportError:
        return
    _orig_load = torchaudio.load

    def _safe_load(path, *args, **kwargs):
        try:
            return _orig_load(path, *args, **kwargs)
        except Exception:
            import soundfile as sf
            import torch
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            wav = torch.from_numpy(data.T).contiguous()
            return wav, sr

    torchaudio.load = _safe_load


_patch_torchaudio_load()

_VOICE_MAP = {
    "binh-an":   "Bình An",
    "xuan-vinh": "Xuân Vĩnh",
    "ngoc-lan":  "Ngọc Lan",
    "my-duyen":  "Mỹ Duyên",
    "truc-ly":   "Trúc Ly",
    "ngoc-linh": "Ngọc Linh",
    "gia-bao":   "Gia Bảo",
    "thai-son":  "Thái Sơn",
    "duc-tri":   "Đức Trí",
    "trong-huu": "Trọng Hữu",
}

# Dấu phiên bản worker — để smoke KHÔNG test nhầm bản cũ + khách/support biết đang
# chạy bản nào. Hậu tố "-cpu" = bản ép device="cpu" (từ 07-05), phân biệt với binary
# GPU-era 06-25 (md5 612f8278…) đang ở gói khách. Chỉ là nhãn — KHÔNG manifest/hash.
BUILD_TAG = "VieNeu Worker 1.36-cpu"


def main():
    # --version: in tag rồi THOÁT NGAY, TRƯỚC khi load model/GPU (chạy nhẹ — dùng để
    # smoke/support xác định bản worker mà không phải khởi tạo model). Đặt trước cả
    # check argv<3 vì `--version` chỉ có 1 tham số.
    if "--version" in sys.argv[1:]:
        print(BUILD_TAG)
        sys.exit(0)
    # Khởi động bình thường: in tag ngay dòng đầu (tái dùng prefix [VIENEU_WORKER] có
    # sẵn → app bắt qua stdout, log smoke thấy đúng bản). Chỉ +1 dòng, không làm chậm.
    print(f"[VIENEU_WORKER] {BUILD_TAG}", flush=True)
    if len(sys.argv) < 3:
        print("Usage: vieneu_worker <batch_json> <voice_id> [ref_audio] [hf_home]",
              file=sys.stderr)
        sys.exit(1)

    batch_file  = sys.argv[1]
    voice_id    = sys.argv[2].lower()
    ref_audio   = sys.argv[3] if len(sys.argv) > 3 else ""
    hf_home     = sys.argv[4] if len(sys.argv) > 4 else ""

    # Trỏ HuggingFace cache về thư mục trong Model Pack (offline mode)
    if hf_home and os.path.isdir(hf_home):
        os.environ["HF_HOME"] = hf_home
        os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(hf_home, "hub")
        os.environ["TRANSFORMERS_CACHE"] = os.path.join(hf_home, "hub")

    if not os.path.exists(batch_file):
        print(f"[VIENEU_WORKER] Không tìm thấy batch file: {batch_file}", file=sys.stderr)
        sys.exit(1)

    with open(batch_file, "r", encoding="utf-8-sig") as f:
        batch = json.load(f)

    if not batch:
        print("[VIENEU_WORKER] Batch rỗng", file=sys.stderr)
        sys.exit(0)

    is_clone = (voice_id == "clone")

    if is_clone and not (ref_audio and os.path.exists(ref_audio)):
        print(f"[VIENEU_WORKER] Thiếu file audio mẫu: {ref_audio}", file=sys.stderr)
        sys.exit(1)

    try:
        from vieneu import Vieneu
    except ImportError:
        print("[VIENEU_WORKER] Chưa cài vieneu: pip install vieneu", file=sys.stderr)
        sys.exit(1)

    vn_voice_name = _VOICE_MAP.get(voice_id)
    display = vn_voice_name if vn_voice_name else ("clone từ " + os.path.basename(ref_audio))
    print(f"[VIENEU_WORKER] Khởi tạo VieNeu v3 Turbo ({display})...")
    sys.stdout.flush()

    # ÉP LUÔN CHẠY CPU/ONNX — KHÔNG dùng GPU/PyTorch cho VieNeu. Lý do (đã test kỹ
    # bằng đo đặc trưng âm thanh trên cả 2 nhánh):
    #   1) Nhánh GPU (PyTorch engine) clone giọng phải đọc file mẫu qua
    #      torchaudio.load → torchaudio 2.11 yêu cầu gói `torchcodec` để decode.
    #      Model Pack KHÔNG bundle torchcodec (cần FFmpeg link riêng, vỡ khi đóng
    #      gói PyInstaller) → torchaudio.load NÉM LỖI. Chỉ "sống" được nhờ bản vá
    #      fallback soundfile (_patch_torchaudio_load) rất mong manh — trên máy
    #      khách / bản .exe nếu vá không áp đúng thì clone hỏng → giọng sai.
    #   2) Nhánh GPU nạp model lên VRAM, máy card 6GB bị đẩy tới ~92% khi infer
    #      batch dài → driver treo cứng (Python không bắt được).
    #   3) Nhánh CPU (OnnxV3LiteEngine) đọc file mẫu bằng soundfile TRỰC TIẾP —
    #      không cần torchcodec/torchaudio, không tốn VRAM, tốc độ ~6-8s/câu
    #      (tương đương GPU), và clone phân biệt giọng đúng (đã đo: 3 ref khác
    #      nhau ra 3 timbre khác nhau rõ rệt). Đây là path "torch-free, nhẹ" mà
    #      chính VieNeu khuyến nghị cho CPU.
    # → Ổn định + đúng giọng + không treo máy > chút tốc độ GPU không đáng kể.
    device = "cpu"

    print(f"[VIENEU_WORKER] Đang tải model lên {device.upper()}, đợi chút...")
    sys.stdout.flush()
    try:
        tts = Vieneu(device=device)
    except Exception as e:
        print(f"[VIENEU_WORKER] Lỗi khởi tạo: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"[VIENEU_WORKER] Model đã sẵn sàng, bắt đầu xử lý từng cảnh...")
    sys.stdout.flush()

    total = len(batch)
    ok_count = 0

    import gc
    import torch

    for i, item in enumerate(batch):
        text = item.get("text", "").strip()
        out_path = item.get("out", "")
        if not text or not out_path:
            continue
        
        # Clear CUDA memory before each inference to ensure maximum free VRAM
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        print(f"[VIENEU_WORKER] Đang đọc cảnh {i+1}/{total}...")
        sys.stdout.flush()

        try:
            if is_clone:
                # Nhiet do/top_k thap hon mac dinh (0.8/25) de bam sat giong mau hon —
                # da do bang spectral centroid + F0: 0.3/10 cho F0 gan voi giong goc hon
                # ro ret (lech ~25Hz) so voi mac dinh (lech ~45Hz). Mac dinh qua "sang tao"
                # (sampling ngau nhien nhieu) lam giong clone bi "trung tinh hoa", nghe
                # giong giong cac giong co san cua VieNeu hon la giong duoc nhan ban.
                audio = tts.infer(text, ref_audio=ref_audio, apply_watermark=False,
                                   temperature=0.3, top_k=10)
            elif vn_voice_name:
                audio = tts.infer(text, voice=vn_voice_name, apply_watermark=False)
            else:
                audio = tts.infer(text, apply_watermark=False)
            
            tts.save(audio, out_path)
            ok_count += 1
        except Exception as e:
            if os.environ.get("VIENEU_DEBUG"):
                import traceback
                traceback.print_exc()
            print(f"[VIENEU_WORKER] Cảnh {i+1} lỗi: {e}", file=sys.stderr)
        finally:
            audio = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        if (i + 1) % 5 == 0 or i == total - 1:
            print(f"[VIENEU_WORKER] {i+1}/{total} cảnh xong")
            sys.stdout.flush()

    # Clear CUDA memory at the end
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print(f"[VIENEU_WORKER] Hoàn tất: {ok_count}/{total} cảnh")
    sys.exit(0)


if __name__ == "__main__":
    main()
