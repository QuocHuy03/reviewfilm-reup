import { PencilLine } from "lucide-react"
import { Button } from "@/components/ui/button"

/** Dịch phụ đề đã xong → mở trình sửa + timeline ngay trên job này; bấm "Dựng lại video" mới tạo job dựng. */
export function ResubButton({ onEdit, resume }: { onEdit: () => void; resume?: boolean }) {
  return (
    <Button size="sm" variant="outline" onClick={onEdit}
      title={resume ? "Mở lại bản đang sửa dở" : "Sửa lời, chỉnh giờ phụ đề & giọng rồi dựng lại — không dịch lại"}>
      <PencilLine /> {resume ? "Sửa tiếp" : "Sửa phụ đề"}
    </Button>
  )
}
