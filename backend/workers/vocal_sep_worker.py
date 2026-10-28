"""Worker tách giọng bằng GPU (onnxruntime-directml) — chạy trong tiến trình riêng.

onnxruntime-directml trùng tên module với onnxruntime thường (OCR dùng) nên cài ở thư mục riêng (RF_ORT_DIR)
và chỉ nạp ở đây.  Dùng:  python vocal_sep_worker.py <model.onnx> <media> <vocals.flac> <music.flac>
Giao tiếp qua stdout:  PROV <provider đang chạy>  ·  PROG <phần trăm>.  Lỗi → stderr + mã thoát ≠ 0.
"""
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

_ORT = os.environ.get('RF_ORT_DIR', '')
if _ORT:
    sys.path.insert(0, _ORT)                                  # onnxruntime-directml được ưu tiên hơn onnxruntime thường
sys.path.insert(1 if _ORT else 0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # backend/ (core.*)


def main():
    (model, media, vp, mp_out) = sys.argv[1:5]
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.log_severity_level = 3
    providers = [p for p in ('DmlExecutionProvider',) if p in ort.get_available_providers()] + ['CPUExecutionProvider']
    sess = ort.InferenceSession(model, so, providers=providers)
    prov = sess.get_providers()[0]
    print(f'PROV {prov}', flush=True)
    if prov != 'DmlExecutionProvider':
        sys.exit(3)                                           # không có GPU → để tiến trình chính chạy CPU (đúng số luồng)
    from core import vocal_sep
    secs = vocal_sep.run_core(sess, media, vp, mp_out, progress=lambda p: print(f'PROG {p}', flush=True))
    if not secs:
        print('không đọc được âm thanh', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
