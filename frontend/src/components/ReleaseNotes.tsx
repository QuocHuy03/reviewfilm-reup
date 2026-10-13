import { FileText, FolderOpen, Info, Sparkles } from "lucide-react"
import { useEffect, useState } from "react"
import { Section } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { AppInfo, ReleaseNote } from "@/types/electron"

const GROUP_LABEL: Record<string, string> = {
  Added: "Thêm mới", Changed: "Thay đổi", Fixed: "Sửa lỗi", Removed: "Gỡ bỏ", Deprecated: "Sắp bỏ", Security: "Bảo mật",
}
const GROUP_TONE: Record<string, string> = {
  Added: "text-success", Changed: "text-primary", Fixed: "text-warning", Removed: "text-destructive",
}

/** Nội dung một mục CHANGELOG (### Nhóm + - dòng) → danh sách có nhóm. */
function NoteBody({ body }: { body: string }) {
  const groups: { name: string; items: string[] }[] = []
  for (const raw of body.split(/\r?\n/)) {
    const line = raw.trim()
    if (line.startsWith("### ")) groups.push({ name: line.slice(4).trim(), items: [] })
    else if (line.startsWith("- ")) {
      if (!groups.length) groups.push({ name: "", items: [] })
      groups[groups.length - 1].items.push(line.slice(2).replace(/`([^`]+)`/g, "$1").replace(/\*\*([^*]+)\*\*/g, "$1"))
    }
  }
  return (
    <div className="flex flex-col gap-3">
      {groups.map((g, i) => (
        <div key={i}>
          {g.name && <p className={`mb-1 text-xs font-semibold ${GROUP_TONE[g.name] ?? ""}`}>{GROUP_LABEL[g.name] ?? g.name}</p>}
          <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] text-muted-foreground">
            {g.items.map((it, j) => <li key={j}>{it}</li>)}
          </ul>
        </div>
      ))}
    </div>
  )
}

function useAppMeta() {
  const bridge = window.rf?.app
  const [info, setInfo] = useState<AppInfo | null>(null)
  const [notes, setNotes] = useState<ReleaseNote[]>([])
  useEffect(() => {
    if (!bridge) return
    bridge.info().then(setInfo).catch(() => {})
    bridge.releaseNotes().then(setNotes).catch(() => {})
  }, [bridge])
  return { info, notes, bridge }
}

/** Hộp thoại "Có gì mới" — tự mở một lần ở lần chạy đầu tiên sau khi cập nhật. */
export function WhatsNewDialog() {
  const { info, notes } = useAppMeta()
  const [open, setOpen] = useState(false)
  const current = notes.find((n) => n.version === info?.version)
  useEffect(() => { if (info?.justUpdated && current) setOpen(true) }, [info, current])
  if (!current || !info) return null
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Có gì mới trong v{current.version}</DialogTitle>
          <DialogDescription>
            Đã cập nhật từ v{info.previousVersion}{current.date ? ` · phát hành ${current.date}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[55vh] overflow-y-auto pr-1"><NoteBody body={current.body} /></div>
        <DialogFooter><Button onClick={() => setOpen(false)}>Đã hiểu</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Mục Giới thiệu trong Cài đặt: phiên bản, môi trường, thư mục dữ liệu/log, lịch sử phiên bản. */
export function AboutPanel() {
  const { info, notes, bridge } = useAppMeta()
  const [showAll, setShowAll] = useState(false)
  if (!bridge || !info) return null
  return (
    <Section title="Giới thiệu" icon={<Info />} desc={`ReviewFilm Studio v${info.version}${info.packaged ? "" : " · dev"}`}>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
        <dt className="text-muted-foreground">Phiên bản</dt><dd className="font-medium tabular">{info.version}</dd>
        <dt className="text-muted-foreground">Electron · Node</dt><dd className="tabular">{info.electron} · {info.node}</dd>
        <dt className="text-muted-foreground">Hệ điều hành</dt><dd>{info.platform}</dd>
      </dl>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => bridge.openData()}><FolderOpen /> Thư mục dữ liệu</Button>
        <Button size="sm" variant="outline" onClick={() => bridge.openLogs()}><FileText /> Mở log</Button>
      </div>
      {notes.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-border pt-3">
          <p className="text-xs font-semibold">Lịch sử phiên bản</p>
          {(showAll ? notes : notes.slice(0, 1)).map((n) => (
            <div key={n.version} className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Badge variant={n.version === info.version ? "default" : "secondary"}>v{n.version}</Badge>
                {n.date && <span className="text-[11px] text-muted-foreground">{n.date}</span>}
              </div>
              <NoteBody body={n.body} />
            </div>
          ))}
          {notes.length > 1 && (
            <Button size="xs" variant="ghost" className="self-start" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Thu gọn" : `Xem tất cả ${notes.length} phiên bản`}
            </Button>
          )}
        </div>
      )}
    </Section>
  )
}
