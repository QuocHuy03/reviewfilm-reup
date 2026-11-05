/** Mức nhận dạng giọng nói — tên hiển thị cho người dùng (giá trị lưu trong cấu hình giữ nguyên: capcut / tiny / base / small…). */
export const ASR_LABELS: Record<string, string> = {
  capcut: "CapCut (online) · chuẩn nhất, khuyên dùng",
  tiny: "Whisper · Siêu nhanh",
  base: "Whisper · Nhanh",
  small: "Whisper · Cân bằng",
  medium: "Whisper · Chính xác",
  large: "Whisper · Chính xác nhất",
  "large-v2": "Whisper · Chính xác cao",
  "large-v3": "Whisper · Chính xác nhất",
}

export const asrLabel = (model?: string) => (model ? ASR_LABELS[model] ?? model : "")

/** Gợi ý ngắn dưới ô chọn mức nhận dạng. */
export const ASR_HINT = "CapCut: cần mạng, nhanh & chuẩn nhất (nhất là tiếng Trung), không cần GPU · Whisper: chạy trên máy, không cần mạng — mức càng cao càng chậm nhưng nghe kỹ hơn"
