/** Mức nhận dạng giọng nói — tên hiển thị cho người dùng (giá trị lưu trong cấu hình giữ nguyên: capcut / tiny / base / small…). */
export const ASR_LABELS: Record<string, string> = {
  capcut: "Online · nhanh nhất",
  tiny: "Siêu nhanh",
  base: "Nhanh",
  small: "Cân bằng",
  medium: "Chính xác",
  large: "Chính xác nhất",
  "large-v2": "Chính xác cao",
  "large-v3": "Chính xác nhất",
}

export const asrLabel = (model?: string) => (model ? ASR_LABELS[model] ?? model : "")

/** Gợi ý ngắn dưới ô chọn mức nhận dạng. */
export const ASR_HINT = "Online: cần mạng, nhanh nhất · Nhanh / Cân bằng: chạy trên máy · Chính xác: chậm hơn, nghe tốt hơn"
