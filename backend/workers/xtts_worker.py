"""
XTTS Worker — batch mode. Load model 1 lan, tong hop tat ca canh.
Usage: python xtts_worker.py <batch_json> <ref_audio> [model_dir]
batch_json format: [{"text": "...", "out": "path/to/vo_NNNN.wav"}, ...]
"""
import sys, os, json
# KHONG set PYTORCH_CUDA_ALLOC_CONF=expandable_segments — option nay khong duoc ho tro
# tren mot so ban torch+CUDA (vd torch 2.0.0+cu118, ban dung de BUILD .exe ban cho khach),
# du chay binh thuong tren may dev (torch+cu126). Da TEST THAT: tren ban khong ho tro,
# loi "Unrecognized CachingAllocator option" khong chi lam mdl.cuda() loi (co the catch
# duoc) ma con LAM HONG CUDA context — thu lai trong CUNG tien trinh se SEGFAULT (crash
# cung, khong bat duoc bang try/except). Nghia la GPU Clone Offline (XTTS) RAT CO THE
# chua tung chay duoc tren ban .exe build cu118 truoc gio (luon roi ve Edge TTS fallback
# ma khong ai biet ly do). Loai bo han option nay — chi la toi uu nho ve phan manh VRAM,
# khong can thiet cho dung/sai ket qua, GPU van chay binh thuong khong co no.

# Phong truong hop ten file/exception co dau tieng Viet tren may console khong UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import warnings

def dummy_showwarning(*args, **kwargs):
    pass
warnings.showwarning = dummy_showwarning
warnings.filterwarnings("ignore")

os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"


def _patch_torchaudio_load():
    """torchaudio moi yeu cau package torchcodec de load audio (vd khi XTTS
    doc file mau qua get_conditioning_latents). Model Pack khong bundle
    torchcodec (can link FFmpeg rieng, de vo khi dong goi PyInstaller).
    Fallback sang soundfile (da co san) khi torchaudio.load loi."""
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

def split_text_by_length(text, max_len=180):
    if len(text) <= max_len:
        return [text]
    import re
    parts = re.split(r'([.,!?;])', text)
    segments = []
    current = ""
    for i in range(0, len(parts), 2):
        chunk = parts[i]
        punc = parts[i+1] if i+1 < len(parts) else ""
        combined = chunk + punc
        if not combined.strip():
            continue
        if len(current) + len(combined) <= max_len:
            current += combined
        else:
            if current:
                segments.append(current.strip())
            if len(combined) > max_len:
                words = combined.split()
                sub_curr = ""
                for w in words:
                    if len(sub_curr) + len(w) + 1 <= max_len:
                        sub_curr += (" " if sub_curr else "") + w
                    else:
                        if sub_curr:
                            segments.append(sub_curr.strip())
                        sub_curr = w
                if sub_curr:
                    current = sub_curr
            else:
                current = combined
    if current:
        segments.append(current.strip())
    return [s for s in segments if s]

_MIN_FREE_VRAM_GB = 1.8  # XTTS + latents can ~1.5-2GB VRAM; duoi nguong nay ep CPU
# de tranh lap lai loi da gap voi VieNeu: may card 6GB bi day toi ~92% VRAM khi
# infer -> driver treo cung ca man hinh (chi di chuot duoc). Kiem tra VRAM TRUOC
# khi .cuda() thay vi doi crash/treo roi moi biet.

def _gpu_has_enough_vram(torch):
    if not torch.cuda.is_available():
        return False
    try:
        free_bytes, _total = torch.cuda.mem_get_info()
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < _MIN_FREE_VRAM_GB:
            print(f"[XTTS] VRAM trống chỉ còn {free_gb:.2f}GB (< {_MIN_FREE_VRAM_GB}GB) "
                  f"— tự chuyển sang CPU để tránh treo máy do quá tải GPU.", flush=True)
            return False
        return True
    except Exception:
        return True  # khong doc duoc VRAM (driver cu) -> cu thu GPU nhu truoc


def _load_model(model_dir, force_cpu=False):
    """Load model 1 lan, tra ve (mdl, cfg, torch, np, sf) de dung chung cho ca
    batch mode (1 lan xong thoat) va server mode (giu song, nhan nhieu yeu cau)."""
    import torch
    import numpy as np
    import soundfile as sf
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    print(f"[XTTS] Loading model tu {model_dir}...", flush=True)
    cfg = XttsConfig()
    cfg.load_json(os.path.join(model_dir, "config.json"))
    mdl = Xtts.init_from_config(cfg)
    mdl.load_checkpoint(cfg, checkpoint_dir=model_dir, eval=True, use_deepspeed=False)
    use_gpu = (not force_cpu) and _gpu_has_enough_vram(torch)
    if use_gpu:
        try:
            mdl.cuda()
            print("[XTTS] GPU san sang.", flush=True)
        except RuntimeError as e:
            print(f"[XTTS] Loi nap GPU ({e}) — chuyen sang CPU.", flush=True)
            mdl.cpu()
            import gc; gc.collect()
            torch.cuda.empty_cache()
            use_gpu = False
    if not use_gpu:
        mdl.cpu()
        print("[XTTS] CPU mode (chay cham hon, nhung on dinh khong treo may).", flush=True)
    return mdl, cfg, torch, np, sf


def _get_conditioning(mdl, cfg, torch, ref_audio):
    print(f"[XTTS] Trich xuat latents tu: {os.path.basename(ref_audio)}", flush=True)
    with torch.no_grad():
        gpt_cond_latent, speaker_embedding = mdl.get_conditioning_latents(
            audio_path=[ref_audio],
            gpt_cond_len=30,
            gpt_cond_chunk_len=6,
            max_ref_length=30,
            sound_norm_refs=cfg.sound_norm_refs,
        )
    return gpt_cond_latent, speaker_embedding


def _warm_up(mdl, cfg, torch, gpt_cond_latent, speaker_embedding):
    print("[XTTS] Warm-up model (tranh artifact canh dau)...", flush=True)
    try:
        with torch.no_grad():
            _wu = mdl.inference(
                "Xin chao ban.", "vi",
                gpt_cond_latent.clone(), speaker_embedding.clone(),
                temperature=0.65, length_penalty=cfg.length_penalty,
                repetition_penalty=5.0, top_k=cfg.top_k, top_p=cfg.top_p,
            )
        del _wu
        import gc; gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[XTTS] Warm-up xong.", flush=True)
    except Exception as _wu_err:
        print(f"[XTTS] Warm-up skip: {_wu_err}", flush=True)


def _infer_one(mdl, cfg, torch, np, sf, gpt_cond_latent, speaker_embedding, text, out_path):
    chunks = split_text_by_length(text, max_len=180)
    wav_list = []
    with torch.no_grad():
        for c in chunks:
            out = mdl.inference(
                c, "vi",
                gpt_cond_latent.clone(), speaker_embedding.clone(),
                temperature=0.65,
                length_penalty=cfg.length_penalty,
                repetition_penalty=5.0,
                top_k=cfg.top_k,
                top_p=cfg.top_p,
            )
            wav_list.append(np.asarray(out["wav"], dtype=np.float32))
    if len(wav_list) > 1:
        silence = np.zeros(int(24000 * 0.15), dtype=np.float32)
        final_wav = wav_list[0]
        for w in wav_list[1:]:
            final_wav = np.concatenate([final_wav, silence, w])
        wav_np = final_wav
    else:
        wav_np = wav_list[0]
    wav_np = np.clip(wav_np, -1.0, 1.0)
    sf.write(out_path, wav_np, 24000, subtype="PCM_16")


def run_server(ref_audio, model_dir):
    """Che do worker THUONG TRUC — giu model + conditioning latents da nap san trong
    RAM/VRAM, nhan lien tuc nhieu yeu cau tong hop tung dong qua stdin (khong phai
    load lai model moi lan nhu batch mode) — dung cho nut 'Nghe thu giong' nghe
    NHANH nhieu cau lien tiep trong luc khach thu giong (kieu CapCut), tranh moi
    lan bam la phai doi 15-30s nap lai model.
    Protocol (1 dong JSON = 1 yeu cau, doc tu stdin, tra loi qua stdout):
      request:  {"text": "...", "out": "path.wav"}   hoac {"cmd": "quit"}
      response: {"ok": true, "out": "path.wav"}  hoac  {"ok": false, "error": "..."}
    """
    import json as _json

    def _is_oom(err) -> bool:
        msg = str(err).lower()
        return "out of memory" in msg or "cuda error" in msg or "cudnn" in msg

    def _boot(force_cpu=False):
        mdl, cfg, torch, np, sf = _load_model(model_dir, force_cpu=force_cpu)
        gpt_cond_latent, speaker_embedding = _get_conditioning(mdl, cfg, torch, ref_audio)
        _warm_up(mdl, cfg, torch, gpt_cond_latent, speaker_embedding)
        return mdl, cfg, torch, np, sf, gpt_cond_latent, speaker_embedding

    try:
        mdl, cfg, torch, np, sf, gpt_cond_latent, speaker_embedding = _boot()
    except Exception as e:
        if _is_oom(e):
            # GPU vua nap vua bi day day VRAM (app khac dang chay cung luc) —
            # thu lai 1 lan bang CPU thay vi treo may/crash luon.
            print(f"[XTTS] GPU lỗi ({e}) — thử lại bằng CPU...", flush=True)
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            try:
                mdl, cfg, torch, np, sf, gpt_cond_latent, speaker_embedding = _boot(force_cpu=True)
            except Exception as e2:
                print(_json.dumps({"ok": False, "ready": False, "error": str(e2)}), flush=True)
                sys.exit(3)
        else:
            print(_json.dumps({"ok": False, "ready": False, "error": str(e)}), flush=True)
            sys.exit(3)

    print(_json.dumps({"ready": True}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = _json.loads(line)
        except Exception as e:
            print(_json.dumps({"ok": False, "error": f"bad json: {e}"}), flush=True)
            continue
        if req.get("cmd") == "quit":
            break
        text = req.get("text", "")
        out_path = req.get("out", "")
        try:
            _infer_one(mdl, cfg, torch, np, sf, gpt_cond_latent, speaker_embedding, text, out_path)
            print(_json.dumps({"ok": True, "out": out_path}), flush=True)
        except Exception as e:
            if _is_oom(e) and next(mdl.parameters()).is_cuda:
                # Qua tai GPU giua chung (app khac vua chiem VRAM) — nap lai
                # toan bo tren CPU roi thu lai CHINH cau nay 1 lan, khong bo cuoc.
                print(f"[XTTS] GPU quá tải giữa phiên ({e}) — chuyển hẳn sang CPU cho các câu sau...", flush=True)
                try:
                    del mdl
                    torch.cuda.empty_cache()
                    mdl, cfg, torch, np, sf, gpt_cond_latent, speaker_embedding = _boot(force_cpu=True)
                    _infer_one(mdl, cfg, torch, np, sf, gpt_cond_latent, speaker_embedding, text, out_path)
                    print(_json.dumps({"ok": True, "out": out_path}), flush=True)
                except Exception as e2:
                    print(_json.dumps({"ok": False, "error": str(e2)}), flush=True)
            else:
                print(_json.dumps({"ok": False, "error": str(e)}), flush=True)
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    sys.exit(0)


def main():
    if len(sys.argv) < 3:
        print("Usage: xtts_worker.py <batch_json> <ref_audio> [model_dir]", file=sys.stderr)
        print("       xtts_worker.py --server <ref_audio> <model_dir>", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--server":
        ref_audio = sys.argv[2]
        model_dir = sys.argv[3] if len(sys.argv) > 3 else None
        run_server(ref_audio, model_dir)
        return

    batch_json_file = sys.argv[1]
    ref_audio = sys.argv[2]
    model_dir_arg = sys.argv[3] if len(sys.argv) > 3 else None

    with open(batch_json_file, "r", encoding="utf-8") as f:
        batch = json.load(f)

    OWN_MODEL   = r"D:\AutoReview_Studio\models\vixtts"
    EDRIC_MODEL = r"D:\edric\EdricAiTextToSpeech\Data\_internal\data"

    model_dir = None
    # Priority: argv[3] → OWN_MODEL → EDRIC_MODEL
    candidates = []
    if model_dir_arg:
        candidates.append(model_dir_arg)
    candidates += [OWN_MODEL, EDRIC_MODEL]
    for d in candidates:
        if os.path.exists(os.path.join(d, "model.pth")):
            model_dir = d
            break

    if not model_dir:
        print("[XTTS] Khong tim thay model. Giai nen ModelPack_v1.0.zip vao thu muc AutoReviewTool/", file=sys.stderr)
        sys.exit(2)

    try:
        import torch
        import numpy as np
        import soundfile as sf
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        print(f"[XTTS] Loading model tu {model_dir}...", flush=True)
        cfg = XttsConfig()
        cfg.load_json(os.path.join(model_dir, "config.json"))
        mdl = Xtts.init_from_config(cfg)
        mdl.load_checkpoint(cfg, checkpoint_dir=model_dir, eval=True, use_deepspeed=False)
        if _gpu_has_enough_vram(torch):
            try:
                mdl.cuda()
                print("[XTTS] GPU san sang.", flush=True)
            except RuntimeError as _gpu_err:
                print(f"[XTTS] Loi nap GPU ({_gpu_err}) — chuyen sang CPU.", flush=True)
                mdl.cpu()
                import gc; gc.collect()
                torch.cuda.empty_cache()
        else:
            mdl.cpu()
            print("[XTTS] CPU mode (chay cham hon, nhung on dinh khong treo may).", flush=True)

        print(f"[XTTS] Trich xuat latents tu: {os.path.basename(ref_audio)}", flush=True)
        # Dung nhieu hon tu file tham chieu (override max 10s cua config)
        with torch.no_grad():
            gpt_cond_latent, speaker_embedding = mdl.get_conditioning_latents(
                audio_path=[ref_audio],
                gpt_cond_len=30,
                gpt_cond_chunk_len=6,
                max_ref_length=30,
                sound_norm_refs=cfg.sound_norm_refs,
            )

        # Warm-up: 1 inference ngắn để khởi động GPT conditioning.
        # Không có warm-up → cảnh đầu tiên bị méo/artifact (cold-start XTTS).
        # QUAN TRỌNG: dùng .clone() để tránh XTTS modify tensor in-place → hỏng 32 cảnh sau.
        print("[XTTS] Warm-up model (tranh artifact canh dau)...", flush=True)
        try:
            with torch.no_grad():
                _wu_result = mdl.inference(
                    "Xin chao ban.", "vi",
                    gpt_cond_latent.clone(),
                    speaker_embedding.clone(),
                    temperature=0.65,
                    length_penalty=cfg.length_penalty,
                    repetition_penalty=5.0,
                    top_k=cfg.top_k,
                    top_p=cfg.top_p,
                )
            del _wu_result
            import gc; gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("[XTTS] Warm-up xong.", flush=True)
        except Exception as _wu_err:
            print(f"[XTTS] Warm-up skip: {_wu_err}", flush=True)

        total = len(batch)
        ok_count = 0
        with torch.no_grad():
            for idx, item in enumerate(batch):
                text     = item["text"]
                out_path = item["out"]
                try:
                    chunks = split_text_by_length(text, max_len=180)
                    wav_list = []
                    for c in chunks:
                        out = mdl.inference(
                            c, "vi",
                            gpt_cond_latent.clone(), speaker_embedding.clone(),
                            temperature=0.65,         # config mac dinh 0.85 qua cao → giong bat on
                            length_penalty=cfg.length_penalty,
                            repetition_penalty=5.0,   # config mac dinh 2.0 qua thap → bi ket am, lap am tiet
                            top_k=cfg.top_k,
                            top_p=cfg.top_p,
                        )
                        chunk_np = np.asarray(out["wav"], dtype=np.float32)
                        wav_list.append(chunk_np)
                    
                    if len(wav_list) > 1:
                        silence = np.zeros(int(24000 * 0.15), dtype=np.float32)
                        final_wav = wav_list[0]
                        for w in wav_list[1:]:
                            final_wav = np.concatenate([final_wav, silence, w])
                        wav_np = final_wav
                    else:
                        wav_np = wav_list[0]

                    wav_np = np.clip(wav_np, -1.0, 1.0)
                    sf.write(out_path, wav_np, 24000, subtype="PCM_16")
                    print(f"[XTTS] [{idx+1}/{total}] OK: {os.path.basename(out_path)}", flush=True)
                    ok_count += 1
                except Exception as e:
                    print(f"[XTTS] [{idx+1}/{total}] FAIL {os.path.basename(out_path)}: {e}",
                          file=sys.stderr, flush=True)
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                finally:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

        print(f"[XTTS] Hoan tat: {ok_count}/{total} canh thanh cong.", flush=True)
        sys.exit(0 if ok_count > 0 else 3)

    except Exception as e:
        print(f"[XTTS] FAIL (khoi dong model): {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
