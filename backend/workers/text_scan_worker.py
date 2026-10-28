"""Worker dò chữ Trung bằng GPU (RapidOCR + onnxruntime-directml) — chạy trong tiến trình riêng.

onnxruntime-directml trùng tên module với onnxruntime thường nên cài ở thư mục riêng (RF_ORT_DIR) và chỉ nạp ở đây.
Nhận việc qua stdin (JSON: video, ranges, interval, geom, cache, total) → chạy core.text_cover._detect, ghi kết quả vào cache.
Giao tiếp qua stdout:  PROV <provider dò chữ>  ·  PROG <đã>/<tổng>  ·  LOG <dòng nhật ký>.
Mã thoát: 0 xong · 3 card không chạy được DirectML · khác = lỗi.
"""
import json
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
    job = json.loads(sys.stdin.read())
    from rapidocr_onnxruntime import RapidOCR
    # chỉ bước dò (chạy mọi khung, ảnh ~1300×736) lên GPU; bước đọc chữ (ít, khung nhỏ đổi cỡ liên tục) để CPU
    ocr = RapidOCR(det_use_dml=True, intra_op_num_threads=4)
    prov = ocr.text_det.infer.session.get_providers()[0]
    print(f'PROV {prov}', flush=True)
    if prov != 'DmlExecutionProvider':
        sys.exit(3)
    from core import text_cover
    (scanned, dets) = text_cover._load_cache(job['cache'])
    text_cover._detect(job['video'], job['ranges'], float(job['interval']), tuple(job['geom']), job['cache'], scanned, dets, ocr,
                       lambda m, *a: print('LOG ' + str(m), flush=True), None,
                       lambda d, t: print(f'PROG {d}/{t}', flush=True), int(job['total']))


if __name__ == '__main__':
    main()
