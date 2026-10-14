import { AlertTriangle } from "lucide-react"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"

type Opts = { title: string; desc?: string; action?: string; cancel?: string; danger?: boolean }
type Req = Opts & { resolve: (ok: boolean) => void }

let push: ((r: Req) => void) | null = null

/** Hỏi xác nhận trước thao tác khó hoàn tác. → true nếu người dùng đồng ý. Cần <ConfirmHost /> trong App. */
export function confirmAction(opts: Opts): Promise<boolean> {
  return new Promise((resolve) => (push ? push({ ...opts, resolve }) : resolve(window.confirm(opts.title))))
}

export function ConfirmHost() {
  const [req, setReq] = useState<Req | null>(null)
  useEffect(() => { push = setReq; return () => { push = null } }, [])
  const close = (ok: boolean) => { req?.resolve(ok); setReq(null) }
  return (
    <Dialog open={!!req} onOpenChange={(o) => { if (!o) close(false) }}>
      <DialogContent className="sm:max-w-md" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {req?.danger && <AlertTriangle className="size-4 text-destructive" />}{req?.title}
          </DialogTitle>
          {req?.desc && <DialogDescription>{req.desc}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>{req?.cancel ?? "Thôi"}</Button>
          <Button variant={req?.danger ? "destructive" : "default"} autoFocus onClick={() => close(true)}>{req?.action ?? "Đồng ý"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
