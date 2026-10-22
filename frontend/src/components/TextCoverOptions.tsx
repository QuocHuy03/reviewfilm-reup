import { ScanText } from "lucide-react"
import { Segmented, ToggleRow } from "@/components/common"

export type TextCover = { auto_cover_text: boolean; text_scan_interval: number; text_blur_strength: number }
export const DEFAULT_TEXT_COVER: TextCover = { auto_cover_text: false, text_scan_interval: 2, text_blur_strength: 22 }

const STRENGTHS = [{ value: "14", label: "Nhẹ" }, { value: "22", label: "Vừa" }, { value: "36", label: "Mạnh" }]

/** AI quét khung hình → làm mờ MỌI chữ tiếng Trung (phụ đề cứng, dải tiêu đề, logo chữ, chữ chèn) đúng chỗ, đúng lúc. */
export function TextCoverOptions({ value, onChange, minutes, reup }: {
  value: TextCover; onChange: (patch: Partial<TextCover>) => void
  /** phút video sẽ quét — để ước tính thời gian (Review: tổng độ dài các cảnh; Reup: cả phim) */
  minutes?: number; reup?: boolean
}) {
  // đo thực tế: ~0.55 giây xử lý / 1 giây phim khi quét mỗi 1s (CPU) — quét 2s nhanh gấp đôi; lần sau dùng lại kết quả
  const est = minutes ? Math.max(1, Math.round((minutes * 60 * 0.55) / value.text_scan_interval / 60)) : null
  return (
    <div className="flex flex-col gap-3">
      <ToggleRow label="Tự che mọi chữ tiếng Trung (AI quét)" checked={value.auto_cover_text} onChange={(v) => onChange({ auto_cover_text: v })}
        desc="Tắt (mặc định): chỉ che phụ đề cũ + chữ / logo ở 4 góc, chữ trong cảnh (biển hiệu, màn hình…) giữ nguyên. Bật: AI che MỌI chữ Trung ở bất kỳ đâu trên hình, đúng chỗ, đúng lúc chữ hiện." />
      {value.auto_cover_text && (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/30 p-3">
          <div className="grid grid-cols-[88px_1fr] items-center gap-x-3 gap-y-2.5">
            <span className="text-[12px] text-muted-foreground">Độ kỹ</span>
            <Segmented size="sm" value={String(value.text_scan_interval)} onChange={(v) => onChange({ text_scan_interval: Number(v) })}
              items={[{ value: "1", label: "Kỹ (1 giây)" }, { value: "2", label: "Nhanh (2 giây)" }]} />
            <span className="text-[12px] text-muted-foreground">Độ mờ</span>
            <Segmented size="sm" value={String(STRENGTHS.reduce((a, s) => Math.abs(+s.value - value.text_blur_strength) < Math.abs(+a.value - value.text_blur_strength) ? s : a).value)}
              onChange={(v) => onChange({ text_blur_strength: Number(v) })} items={STRENGTHS} />
          </div>
          <p className="flex gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
            <ScanText className="mt-0.5 size-3.5 shrink-0" />
            <span>
              {value.text_scan_interval <= 1 ? "Kỹ: bắt cả chữ hiện thoáng qua." : "Nhanh: đủ cho phụ đề và tiêu đề — chữ hiện dưới 2 giây có thể sót."}
              {est != null ? ` Thêm khoảng ${est} phút quét ${reup ? "cả phim" : "các cảnh dùng"}`
                : ` Thời gian quét ≈ ${value.text_scan_interval <= 1 ? "½" : "¼"} độ dài ${reup ? "phim" : "các cảnh dùng"}`}
              {" (chỉ lần đầu — dựng lại dùng kết quả cũ)."}
            </span>
          </p>
        </div>
      )}
    </div>
  )
}
