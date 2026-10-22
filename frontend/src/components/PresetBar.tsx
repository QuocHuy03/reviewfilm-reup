import { BookmarkPlus, Layers, Loader2, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { confirmAction } from "@/components/ConfirmHost"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type { Preset } from "@/lib/types"

/**
 * Mẫu cấu hình theo kênh: lưu toàn bộ cấu hình trang Tạo video (giọng, phụ đề, vùng che, logo/intro/outro,
 * khung hình, hậu kỳ…) thành mẫu có tên — chọn mẫu là điền lại hết. Không lưu nguồn video.
 */
export function PresetBar<C extends Record<string, unknown>>({ mode, cfg, onApply, bare }: {
  mode: string; cfg: C; onApply: (mode: string, cfg: Partial<C>) => void
  /** Không khung, gọn — nằm trong thanh trên cùng của trang Tạo video */
  bare?: boolean
}) {
  const [items, setItems] = useState<Preset[]>([])
  const [current, setCurrent] = useState("")
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.presets().then(setItems).catch(() => {}) }, [])

  const apply = (n: string) => {
    const p = items.find((x) => x.name === n)
    if (!p) return
    setCurrent(n)
    onApply(p.mode, p.cfg as Partial<C>)
    toast.success(`Đã áp dụng mẫu "${n}"`)
  }
  const save = async () => {
    setBusy(true)
    try {
      setItems(await api.savePreset(name.trim(), mode, cfg))
      setCurrent(name.trim()); setOpen(false)
      toast.success(`Đã lưu mẫu "${name.trim()}"`)
    } catch (e) { toast.error("Không lưu được mẫu", { description: (e as Error).message }) }
    finally { setBusy(false) }
  }
  const remove = async () => {
    if (!current || !await confirmAction({ title: `Xoá mẫu "${current}"?`, danger: true, action: "Xoá mẫu" })) return
    try { setItems(await api.deletePreset(current)); setCurrent("") } catch (e) { toast.error((e as Error).message) }
  }

  return (
    <div className={cn("flex items-center gap-2", !bare && "rounded-xl border border-border bg-card px-3 py-2")}>
      <Layers className="size-4 shrink-0 text-primary" />
      <span className={cn("shrink-0 text-[13px] font-medium", bare && "sr-only")}>Mẫu kênh</span>
      <Select value={current} onValueChange={apply}>
        <SelectTrigger size="sm" className={bare ? "w-36 xl:w-48" : "w-56"} title="Mẫu kênh — điền sẵn giọng, phụ đề, logo, intro/outro…"><SelectValue placeholder={bare ? (items.length ? "Chọn mẫu kênh…" : "Mẫu kênh") : (items.length ? "Chọn mẫu để điền sẵn…" : "Chưa có mẫu nào")} /></SelectTrigger>
        <SelectContent>
          {items.map((p) => (
            <SelectItem key={p.name} value={p.name}>
              {p.name}<span className="ml-1.5 text-[10.5px] text-muted-foreground">· {p.mode === "reup" ? "Dịch & Reup" : "Review"}</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {current && <Button variant="ghost" size="icon-sm" title="Xoá mẫu này" onClick={remove}><Trash2 /></Button>}
      {!bare && <span className="ml-auto hidden text-[11px] text-muted-foreground xl:inline">Lưu giọng, phụ đề, logo, intro/outro… để dùng lại cho kênh</span>}
      <Button variant="outline" size="sm" title="Lưu cấu hình hiện tại thành mẫu kênh" onClick={() => { setName(current); setOpen(true) }}>
        <BookmarkPlus /> {bare ? <span className="hidden xl:inline">Lưu mẫu</span> : "Lưu thành mẫu"}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Lưu cấu hình thành mẫu</DialogTitle>
            <DialogDescription>Lưu toàn bộ cấu hình hiện tại (trừ video nguồn). Trùng tên sẽ ghi đè mẫu cũ.</DialogDescription>
          </DialogHeader>
          <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="VD: Kênh Phim Hay, Kênh Shorts 9:16"
            onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) save() }} />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Thôi</Button>
            <Button onClick={save} disabled={busy || !name.trim()}>{busy ? <Loader2 className="animate-spin" /> : <BookmarkPlus />} Lưu mẫu</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
