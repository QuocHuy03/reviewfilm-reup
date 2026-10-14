import {
  AlertTriangle, Check, CheckCircle2, Circle, Clapperboard, Eye, EyeOff, Film, List as ListIcon, Loader2, Minus, Music, Pause, Play, Plus,
  Redo2, RefreshCw, Scissors, Settings, Sparkles, Undo2, Wand2, X, XCircle,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { PathInput, Segmented, ToggleRow } from "@/components/common"
import { Monitor, subtitleChunk } from "@/components/timeline/Monitor"
import { Timeline } from "@/components/timeline/Timeline"
import { useTimelinePlayer } from "@/components/timeline/useTimelinePlayer"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { useAudio } from "@/hooks/useAudio"
import { api, bridge, mediaUrl } from "@/lib/api"
import { basename, fmtClock, fmtDuration } from "@/lib/format"
import type { AiEdit, JobDetail, Scene } from "@/lib/types"
import { cn } from "@/lib/utils"
import { checkScenes, fixDurations, issueLevels, type Issue } from "./checks"
import { SaveBadge } from "./SaveBadge"
import { StageHeader } from "./StageHeader"
import { draftFor, useDraftAutosave } from "@/hooks/useDraft"
import { confirmAction } from "@/components/ConfirmHost"

type Mixer = { original_volume: number; bgm_path: string; bgm_volume: number; audio_ducking: boolean }
type StepState = "pending" | "running" | "done" | "skip" | "error"
type AutoStep = { label: string; state: StepState; detail?: string }
type AutoRun = { steps: AutoStep[]; running: boolean; backup: Scene[]; summary?: string; needLogin?: boolean }

/**
 * Trình hậu kỳ ở bước "Xem trước": Monitor + bảng tab (Cảnh · Âm thanh · Kiểm tra · AI hậu kỳ) + Timeline.
 * Mọi chỉnh sửa giữ ở client; "Xuất video" gửi kịch bản + mixer về backend để dựng.
 */
export function PostEditor({ job }: { job: JobDetail }) {
  const { play, playing, stop } = useAudio()
  const draft = draftFor(job, "preview")
  const [scenes, setScenes] = useState<Scene[]>(draft?.scenes ?? job.scenes)
  const [regen, setRegen] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<"timeline" | "list">("timeline")
  const [tab, setTab] = useState("scene")
  const [subVisible, setSubVisible] = useState(true)
  const { options, go } = useStore()
  const subLayout = options?.sub_layouts[String((job.config as Record<string, unknown>).sub_layout ?? "")]
  const subChars = subLayout ? subLayout.sub_max_chars_per_chunk * Math.max(1, subLayout.sub_max_lines) : 80
  const [mixer, setMixer] = useState<Mixer>({ original_volume: 8, bgm_path: "", bgm_volume: 5, audio_ducking: true, ...(draft?.mixer as Partial<Mixer> | undefined) })
  const saveState = useDraftAutosave(job.id, scenes, mixer as unknown as Record<string, unknown>)
  useEffect(() => { if (draft) toast.info("Đã mở lại bản đang sửa dở") }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const mode = job.kind === "reup" ? "reup" : "review"
  const player = useTimelinePlayer({ scenes, bgmPath: mixer.bgm_path, bgmVolume: mixer.bgm_volume, originalVolume: mixer.original_volume, mode })
  const [selected, setSelected] = useState<number | null>(player.clips[0]?.index ?? null)
  const issues = useMemo(() => checkScenes(scenes, mode), [scenes, mode])
  const levels = useMemo(() => issueLevels(issues), [issues])
  const errors = issues.filter((i) => i.level === "error").length
  const [auto, setAuto] = useState<AutoRun | null>(null)
  const scenesRef = useRef(scenes)
  scenesRef.current = scenes

  // Đầu phát chạy qua cảnh nào thì chọn cảnh đó
  useEffect(() => { if (player.playing && player.currentClip) setSelected(player.currentClip.index) }, [player.playing, player.currentClip])

  // Phím tắt: Space phát/dừng, ← → chuyển cảnh (bỏ qua khi đang gõ chữ)
  useEffect(() => {
    if (view !== "timeline") return
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === "TEXTAREA" || tag === "INPUT") return
      if (e.code === "Space") { e.preventDefault(); stop(); player.toggle() }
      if ((e.ctrlKey || e.metaKey) && e.code === "KeyZ") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return }
      if ((e.ctrlKey || e.metaKey) && e.code === "KeyY") { e.preventDefault(); redo(); return }
      if ((e.code === "Delete" || e.code === "Backspace") && selected !== null) { e.preventDefault(); toggleExcluded(selected); return }
      if (e.altKey && (e.code === "ArrowRight" || e.code === "ArrowLeft") && selected !== null) {
        e.preventDefault()
        const k = player.clips.findIndex((c) => c.index === selected)
        if (k < 0) return
        if (e.code === "ArrowLeft" && k > 0) reorder(selected, player.clips[k - 1].index)
        if (e.code === "ArrowRight" && k < player.clips.length - 1) reorder(selected, player.clips[k + 2]?.index ?? scenesRef.current.length)
        return
      }
      if (e.code === "ArrowRight" || e.code === "ArrowLeft") {
        e.preventDefault()
        const i = player.clips.findIndex((c) => c.index === selected)
        const c = player.clips[Math.max(0, Math.min(player.clips.length - 1, i + (e.code === "ArrowRight" ? 1 : -1)))]
        if (c) { setSelected(c.index); player.seek(c.start) }
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [view, player, selected, stop]) // eslint-disable-line react-hooks/exhaustive-deps

  const update = (i: number, patch: Partial<Scene>) => setScenes((prev) => prev.map((x, j) => (j === i ? { ...x, ...patch } : x)))

  const select = (i: number) => {
    setSelected(i)
    const c = player.clips.find((x) => x.index === i)
    if (c) player.seek(c.start)
  }

  /** Tạo lại giọng 1 cảnh từ lời hiện tại (backend lưu vào job). */
  const regenerate = async (i: number, text = scenesRef.current[i].voiceover, preview = true): Promise<Scene | null> => {
    player.pause()
    setRegen(i)
    try {
      const updated = await api.regenScene(job.id, i, text, scenesRef.current[i])
      const merged = (x: Scene) => ({ ...x, ...updated, voiceover: text, excluded: x.excluded, clip_start: x.clip_start, clip_end: x.clip_end })
      scenesRef.current = scenesRef.current.map((x, j) => (j === i ? merged(x) : x))
      setScenes((prev) => prev.map((x, j) => (j === i ? merged(x) : x)))
      if (preview) play(mediaUrl(updated.tts_path!))
      return scenesRef.current[i]
    } catch (e) {
      toast.error(`Cảnh #${i + 1}: ${(e as Error).message}`)
      return null
    } finally { setRegen(null) }
  }

  /** Đặt kịch bản mới ngay (state + ref) — để các bước sau của chuỗi tự hậu kỳ đọc được. */
  const commit = (next: Scene[]) => { scenesRef.current = next; setScenes(next) }

  // ── Hoàn tác / làm lại cho chỉnh sửa trên timeline (cắt mép, đổi thứ tự, bỏ cảnh) ──
  const past = useRef<Scene[][]>([])
  const future = useRef<Scene[][]>([])
  const [, setHistoryTick] = useState(0)
  const snapshot = () => {
    past.current = [...past.current.slice(-49), scenesRef.current]
    future.current = []
    setHistoryTick((n) => n + 1)
  }
  const undo = () => {
    const prev = past.current.pop()
    if (!prev) return
    future.current.push(scenesRef.current)
    commit(prev)
    setHistoryTick((n) => n + 1)
  }
  const redo = () => {
    const next = future.current.pop()
    if (!next) return
    past.current.push(scenesRef.current)
    commit(next)
    setHistoryTick((n) => n + 1)
  }

  /** Đưa cảnh `from` tới trước cảnh `to` (to = số cảnh → cuối). Lời, giọng, phụ đề, đoạn hình đi cùng nhau. */
  const reorder = (from: number, to: number) => {
    snapshot()
    const next = [...scenesRef.current]
    const [moved] = next.splice(from, 1)
    const at = to > from ? to - 1 : to
    next.splice(at, 0, moved)
    commit(next)
    setSelected(at)
  }

  // Sửa từ các tab: lưu bản Hoàn tác trước mỗi thay đổi; gõ chữ liên tục trong 1 cảnh gộp thành 1 bước (nghỉ > 1.5s = bước mới)
  const lastText = useRef<{ i: number; t: number }>({ i: -1, t: 0 })
  const edit = (i: number, patch: Partial<Scene>) => {
    const typing = "voiceover" in patch || "subtitle" in patch
    const now = Date.now()
    if (!typing || lastText.current.i !== i || now - lastText.current.t > 1500) snapshot()
    lastText.current = typing ? { i, t: now } : { i: -1, t: 0 }
    update(i, patch)
  }

  const toggleExcluded = (i: number) => {
    snapshot()
    update(i, { excluded: !scenesRef.current[i].excluded })
  }

  /**
   * Tự hậu kỳ một chạm:
   *   1. căn đoạn hình theo lời đọc  2. AI (ChatGPT/Gemini) rà & sửa kịch bản  3. tạo lại giọng câu đã sửa
   *   4. căn lại theo giọng mới. Có "Hoàn tác" về bản trước khi chạy.
   */
  const autoPost = async () => {
    player.pause(); stop()
    const steps: AutoStep[] = [
      { label: "Căn đoạn hình khớp lời đọc", state: "pending" },
      { label: "AI rà & sửa kịch bản", state: "pending" },
      { label: "Tạo lại giọng các câu đã sửa", state: "pending" },
      { label: "Căn lại theo giọng mới", state: "pending" },
    ]
    const run: AutoRun = { steps, running: true, backup: scenesRef.current }
    const set = (i: number, patch: Partial<AutoStep>) => { steps[i] = { ...steps[i], ...patch }; setAuto({ ...run, steps: [...steps] }) }
    setAuto({ ...run })

    set(0, { state: "running" })
    const f1 = fixDurations(scenesRef.current, player.videoDuration)
    commit(f1.scenes)
    set(0, { state: "done", detail: f1.changed.length ? `Đã chỉnh ${f1.changed.length} cảnh` : "Không cần chỉnh" })

    let voiceChanged: { i: number; text: string }[] = []
    let aiCount = 0
    set(1, { state: "running" })
    const sys = await api.system().catch(() => null)
    const connected = Boolean(sys?.web_ai?.chatgpt || sys?.web_ai?.gemini)
    if (!connected) {
      set(1, { state: "skip", detail: "Chưa kết nối ChatGPT / Gemini" })
      run.needLogin = true
    } else {
      try {
        const { edits } = await api.aiPolish(job.id, scenesRef.current)
        aiCount = edits.length
        const next = scenesRef.current.map((x) => ({ ...x }))
        for (const e of edits) {
          const sc = next[e.id]
          if (!sc) continue
          if (e.exclude) { sc.excluded = true; continue }
          if (e.subtitle) sc.subtitle = e.subtitle
          if (e.voiceover) {
            sc.voiceover = e.voiceover
            if (job.kind === "review") sc.subtitle = e.voiceover
            voiceChanged.push({ i: e.id, text: e.voiceover })
          }
        }
        commit(next)
        set(1, { state: "done", detail: edits.length ? `${edits.length} chỉnh sửa (${edits.filter((e) => e.exclude).length} cảnh bỏ)` : "Kịch bản đã ổn" })
      } catch (err) {
        set(1, { state: "error", detail: (err as Error).message })
        voiceChanged = []
      }
    }

    set(2, { state: voiceChanged.length ? "running" : "skip", detail: voiceChanged.length ? `0/${voiceChanged.length}` : "Không có câu cần tạo lại" })
    let ok = 0
    for (const [k, v] of voiceChanged.entries()) {
      if (await regenerate(v.i, v.text, false)) ok++
      set(2, { detail: `${k + 1}/${voiceChanged.length}` })
    }
    if (voiceChanged.length) set(2, { state: ok === voiceChanged.length ? "done" : "error", detail: `${ok}/${voiceChanged.length} câu` })

    set(3, { state: "running" })
    const f2 = fixDurations(scenesRef.current, player.videoDuration)
    commit(f2.scenes)
    set(3, { state: "done", detail: f2.changed.length ? `Đã chỉnh ${f2.changed.length} cảnh` : "Đã khớp" })

    const left = checkScenes(scenesRef.current).length
    run.running = false
    run.summary = `Đã căn ${new Set([...f1.changed, ...f2.changed]).size} đoạn hình, AI sửa ${aiCount} mục, tạo lại ${ok} giọng. ${left ? `Còn ${left} vấn đề — xem tab Kiểm tra.` : "Không còn vấn đề."}`
    setAuto({ ...run, steps: [...steps] })
  }

  const submit = async (confirmed: boolean) => {
    stop(); player.pause(); setBusy(true)
    try {
      await api.confirm(job.id, confirmed ? {
        confirmed, scenes, mixer: { original_volume: mixer.original_volume / 100, bgm_path: mixer.bgm_path, bgm_volume: mixer.bgm_volume / 100, audio_ducking: mixer.audio_ducking },
      } : { confirmed })
      toast.success(confirmed ? "Đang dựng video…" : "Đã huỷ job")
    } catch (e) { toast.error((e as Error).message); setBusy(false) }   // thành công: giữ khoá nút tới khi chuyển bước
  }

  const current = player.currentClip
  const currentScene = current ? scenes[current.index] : null

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
      <StageHeader title="Hậu kỳ & xác nhận" dot="bg-warning animate-pulse"
        meta={<span className="flex items-center gap-2">
          <span>{player.clips.length}/{scenes.length} cảnh · {fmtDuration(player.total)}</span>
          <SaveBadge state={saveState} />
          {issues.length > 0 ? (
            <button className={cn("flex items-center gap-1 font-medium", errors ? "text-destructive" : "text-warning")} onClick={() => setTab("checks")}>
              <AlertTriangle className="size-3" /> {issues.length} vấn đề
            </button>
          ) : <span className="flex items-center gap-1 text-success"><CheckCircle2 className="size-3" /> Không có lỗi</span>}
        </span>}
        actions={<>
          <div className="flex items-center">
            <Button variant="ghost" size="icon-sm" title="Hoàn tác (Ctrl+Z)" disabled={!past.current.length} onClick={undo}><Undo2 /></Button>
            <Button variant="ghost" size="icon-sm" title="Làm lại (Ctrl+Y)" disabled={!future.current.length} onClick={redo}><Redo2 /></Button>
          </div>
          <Segmented size="sm" value={view} onChange={setView} items={[{ value: "timeline", label: "Timeline", icon: <Clapperboard /> }, { value: "list", label: "Danh sách", icon: <ListIcon /> }]} />
          <Button variant="outline" size="sm" onClick={autoPost} disabled={busy || regen !== null || auto?.running}
            title="Căn hình theo lời + AI (ChatGPT/Gemini) sửa kịch bản + tạo lại giọng — tự động">
            {auto?.running ? <Loader2 className="animate-spin" /> : <Wand2 />} Tự hậu kỳ
          </Button>
          <Button variant="ghost" size="sm" disabled={busy} onClick={async () => {
            if (await confirmAction({ title: "Huỷ job?", danger: true, action: "Huỷ job", cancel: "Tiếp tục sửa",
              desc: "Job sẽ dừng và không xuất video. Các chỉnh sửa ở bước này sẽ không được dùng." })) submit(false)
          }}>Huỷ job</Button>
          <Button size="sm" onClick={() => submit(true)} disabled={busy || regen !== null || player.clips.length === 0}
            title={errors ? "Còn lỗi — vẫn có thể xuất, nhưng nên sửa trước" : undefined}>
            {busy ? <Loader2 className="animate-spin" /> : <Film />} Xuất video
          </Button>
        </>} />

      <AutoDialog auto={auto} onClose={() => setAuto(null)} onUndo={() => { if (auto) commit(auto.backup); setAuto(null); toast("Đã hoàn tác về bản trước khi tự hậu kỳ") }}
        onLogin={() => { setAuto(null); go("settings") }} />

      {view === "timeline" ? (
        <>
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(360px,430px)]">
            <Monitor videoPath={job.result.video_path} attachVideo={player.attachVideo} time={player.time} total={player.total}
              subtitle={subVisible && currentScene && current
                ? subtitleChunk(currentScene.subtitle || currentScene.voiceover || "", player.time - current.start, current.dur, subChars)
                : ""}
              label={current ? `Cảnh ${player.clips.indexOf(current) + 1}/${player.clips.length}` : ""} />

            <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-col gap-0 border-l border-border">
              <TabsList className="m-2 grid w-auto grid-cols-4">
                <TabsTrigger value="scene"><Scissors /> Cảnh</TabsTrigger>
                <TabsTrigger value="audio"><Music /> Âm thanh</TabsTrigger>
                <TabsTrigger value="checks" className="gap-1">
                  <AlertTriangle /> Kiểm tra
                  {issues.length > 0 && <span className={cn("rounded-full px-1 text-[9px] text-white", errors ? "bg-destructive" : "bg-warning")}>{issues.length}</span>}
                </TabsTrigger>
                <TabsTrigger value="ai"><Sparkles /> AI</TabsTrigger>
              </TabsList>
              <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
                <TabsContent value="scene">
                  <SceneTab job={job} scenes={scenes} selected={selected} issues={issues} regen={regen}
                    update={edit} regenerate={regenerate} onPlay={(i) => { const c = player.clips.find((x) => x.index === i); stop(); if (c) player.play(c.start) }} />
                </TabsContent>
                <TabsContent value="audio"><AudioTab mixer={mixer} setMixer={setMixer} /></TabsContent>
                <TabsContent value="checks"><ChecksTab issues={issues} onPick={(i) => { select(i); setTab("scene") }} /></TabsContent>
                <TabsContent value="ai">
                  <AiTab job={job} scenes={scenes} regen={regen} update={edit} regenerate={regenerate} onPick={select} />
                </TabsContent>
              </div>
            </Tabs>
          </div>
          <Timeline scenes={scenes} clips={player.clips} total={player.total} time={player.time} playing={player.playing}
            selected={selected} muted={player.muted} bgmName={mixer.bgm_path ? basename(mixer.bgm_path) : ""} issues={levels}
            mode={mode} videoDuration={Number.isFinite(player.videoDuration) ? player.videoDuration : undefined}
            onTrim={(i, patch) => update(i, patch)} onEditStart={snapshot} onPeek={player.peek} onReorder={reorder}
            subtitleVisible={subVisible} onToggleSubtitle={() => setSubVisible((v) => !v)}
            onSeek={player.seek} onSelect={setSelected} onToggle={() => { stop(); player.toggle() }} onToggleMute={player.toggleMute} />
        </>
      ) : (
        <SceneList scenes={scenes} regen={regen} levels={levels} playing={playing}
          onPlay={(url) => { player.pause(); play(url) }} update={edit} regenerate={(i) => regenerate(i)} />
      )}
    </div>
  )
}

/* ─────────────────────────────── Hộp thoại tự hậu kỳ ─────────────────────────────── */
function AutoDialog({ auto, onClose, onUndo, onLogin }: { auto: AutoRun | null; onClose: () => void; onUndo: () => void; onLogin: () => void }) {
  const icon = (st: StepState) => st === "running" ? <Loader2 className="size-4 animate-spin text-primary" />
    : st === "done" ? <CheckCircle2 className="size-4 text-success" />
    : st === "error" ? <XCircle className="size-4 text-destructive" />
    : st === "skip" ? <Circle className="size-4 text-muted-foreground/50" />
    : <Circle className="size-4 text-muted-foreground" />
  return (
    <Dialog open={!!auto} onOpenChange={(o) => { if (!o && !auto?.running) onClose() }}>
      <DialogContent className="max-w-md" showCloseButton={!auto?.running}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Wand2 className="size-4 text-primary" /> Tự hậu kỳ</DialogTitle>
          <DialogDescription>{auto?.running ? "Đang xử lý — đừng đóng cửa sổ." : auto?.summary}</DialogDescription>
        </DialogHeader>
        <ol className="flex flex-col gap-3">
          {auto?.steps.map((st, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="mt-0.5">{icon(st.state)}</span>
              <div className="min-w-0">
                <p className={cn("text-[13px]", st.state === "pending" && "text-muted-foreground")}>{st.label}</p>
                {st.detail && <p className={cn("text-[11px]", st.state === "error" ? "text-destructive" : "text-muted-foreground")}>{st.detail}</p>}
              </div>
            </li>
          ))}
        </ol>
        {!auto?.running && (
          <DialogFooter className="gap-2 sm:justify-between">
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={onUndo}><Undo2 /> Hoàn tác</Button>
              {auto?.needLogin && <Button variant="outline" size="sm" onClick={onLogin}><Settings /> Kết nối ChatGPT / Gemini</Button>}
            </div>
            <Button size="sm" onClick={onClose}>Xong</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

/* ─────────────────────────────── Tab: Cảnh ─────────────────────────────── */
function SceneTab({ job, scenes, selected, issues, regen, update, regenerate, onPlay }: {
  job: JobDetail; scenes: Scene[]; selected: number | null; issues: Issue[]; regen: number | null
  update: (i: number, p: Partial<Scene>) => void; regenerate: (i: number) => Promise<Scene | null>; onPlay: (i: number) => void
}) {
  if (selected === null || !scenes[selected]) return <p className="py-10 text-center text-xs text-muted-foreground">Chọn một cảnh trên timeline</p>
  const s = scenes[selected]
  const mine = issues.filter((x) => x.index === selected)
  const src = Math.max(0, s.clip_end - s.clip_start)
  const showSub = job.kind === "reup" || (s.subtitle !== undefined && s.subtitle !== s.voiceover)
  const nudge = (field: "clip_start" | "clip_end", d: number) => {
    const v = Math.max(0, +(s[field] + d).toFixed(2))
    if (field === "clip_start" && v >= s.clip_end - 0.2) return
    if (field === "clip_end" && v <= s.clip_start + 0.2) return
    update(selected, { [field]: v })
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">Cảnh #{selected + 1}</span>
        {s._tts_engine_used && <span className="rounded bg-muted px-1.5 text-[10px] uppercase">{s._tts_engine_used}</span>}
        {s.excluded && <span className="rounded bg-destructive/10 px-1.5 text-[10px] text-destructive">đã bỏ</span>}
        <div className="ml-auto flex gap-1">
          <Button size="icon-sm" variant="outline" disabled={s.excluded} title="Nghe cảnh" onClick={() => onPlay(selected)}><Play /></Button>
          <Button size="icon-sm" variant="ghost" title={s.excluded ? "Dùng lại cảnh" : "Bỏ cảnh"} onClick={() => update(selected, { excluded: !s.excluded })}>
            {s.excluded ? <Eye /> : <EyeOff />}
          </Button>
        </div>
      </div>

      {mine.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border border-warning/30 bg-warning/5 p-2">
          {mine.map((m) => (
            <p key={m.code} className={cn("flex gap-1.5 text-[11px]", m.level === "error" ? "text-destructive" : "text-warning")}>
              <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {m.message}
            </p>
          ))}
        </div>
      )}

      <Group label="Đoạn hình gốc" hint={`${src.toFixed(1)}s hình · ${(s.tts_duration ?? 0).toFixed(1)}s lời`}>
        <div className="grid grid-cols-2 gap-2">
          <TimeField label="Bắt đầu" value={s.clip_start} onNudge={(d) => nudge("clip_start", d)} onSet={(v) => v < s.clip_end - 0.2 && update(selected, { clip_start: v })} />
          <TimeField label="Kết thúc" value={s.clip_end} onNudge={(d) => nudge("clip_end", d)} onSet={(v) => v > s.clip_start + 0.2 && update(selected, { clip_end: v })} />
        </div>
      </Group>

      <Group label="Lời đọc" hint={`${(s.voiceover || "").trim().split(/\s+/).filter(Boolean).length} từ`}>
        <Textarea value={s.voiceover} rows={5} className="resize-y text-[13px]" onChange={(e) => update(selected, { voiceover: e.target.value })} />
        <Button size="sm" variant="outline" className="self-start" disabled={regen !== null} onClick={() => regenerate(selected)}>
          {regen === selected ? <Loader2 className="animate-spin" /> : <RefreshCw />} Tạo lại giọng
        </Button>
      </Group>

      {showSub && (
        <Group label="Phụ đề" hint="hiện trên video">
          <Textarea value={s.subtitle ?? ""} rows={3} className="resize-y text-[13px]" onChange={(e) => update(selected, { subtitle: e.target.value })} />
        </Group>
      )}
    </div>
  )
}

function Group({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium">{label}</span>
        {hint && <span className="tabular text-[10.5px] text-muted-foreground">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function TimeField({ label, value, onNudge, onSet }: { label: string; value: number; onNudge: (d: number) => void; onSet: (v: number) => void }) {
  const [text, setText] = useState(value.toFixed(1))
  useEffect(() => setText(value.toFixed(1)), [value])
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10.5px] text-muted-foreground">{label} · {fmtClock(value)}</span>
      <div className="flex items-center gap-1">
        <Button size="icon-xs" variant="outline" onClick={() => onNudge(-0.5)} title="-0.5s"><Minus /></Button>
        <Input value={text} onChange={(e) => setText(e.target.value)} className="tabular h-7 px-1.5 text-center font-mono text-xs"
          onBlur={() => { const v = parseFloat(text); if (Number.isFinite(v) && v >= 0) onSet(+v.toFixed(2)); else setText(value.toFixed(1)) }}
          onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur() }} />
        <Button size="icon-xs" variant="outline" onClick={() => onNudge(0.5)} title="+0.5s"><Plus /></Button>
      </div>
    </div>
  )
}

/* ─────────────────────────────── Tab: Âm thanh ─────────────────────────────── */
function AudioTab({ mixer, setMixer }: { mixer: Mixer; setMixer: (m: Mixer) => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Group label="Tiếng gốc của phim" hint={`${mixer.original_volume}%`}>
        <Slider value={[mixer.original_volume]} max={100} onValueChange={([v]) => setMixer({ ...mixer, original_volume: v })} />
      </Group>
      <Group label="Nhạc nền">
        <PathInput value={mixer.bgm_path} onChange={(v) => setMixer({ ...mixer, bgm_path: v })} pick={bridge.pickAudio} placeholder="Chọn file nhạc (tuỳ chọn)" />
      </Group>
      <Group label="Âm lượng nhạc nền" hint={`${mixer.bgm_volume}%`}>
        <Slider value={[mixer.bgm_volume]} max={50} disabled={!mixer.bgm_path} onValueChange={([v]) => setMixer({ ...mixer, bgm_volume: v })} />
      </Group>
      <ToggleRow label="Tự nén nhạc khi có lời" desc="Nhạc nhỏ lại lúc đang đọc, to lên ở khoảng lặng." checked={mixer.audio_ducking}
        onChange={(v) => setMixer({ ...mixer, audio_ducking: v })} disabled={!mixer.bgm_path} />
      <p className="text-[11px] text-muted-foreground">Nút <b>M</b> trên timeline chỉ tắt tiếng khi nghe thử, không ảnh hưởng video xuất ra.</p>
    </div>
  )
}

/* ─────────────────────────────── Tab: Kiểm tra ─────────────────────────────── */
function ChecksTab({ issues, onPick }: { issues: Issue[]; onPick: (i: number) => void }) {
  if (!issues.length) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <CheckCircle2 className="size-7 text-success" />
        <p className="text-sm font-medium">Không phát hiện vấn đề</p>
        <p className="text-xs text-muted-foreground">Lời đọc, giọng và độ dài hình đều ổn.</p>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1.5">
      <p className="mb-1 text-[11px] text-muted-foreground">Bấm vào một mục để mở cảnh đó.</p>
      {issues.map((it, k) => (
        <button key={k} onClick={() => onPick(it.index)}
          className="flex items-start gap-2 rounded-md border border-border px-2.5 py-2 text-left hover:border-primary/40 hover:bg-muted/40">
          <span className={cn("tabular mt-0.5 shrink-0 rounded px-1 text-[10px] font-semibold text-white", it.level === "error" ? "bg-destructive" : "bg-warning")}>#{it.index + 1}</span>
          <span className="text-xs">{it.message}</span>
        </button>
      ))}
    </div>
  )
}

/* ─────────────────────────────── Tab: AI hậu kỳ ─────────────────────────────── */
function AiTab({ job, scenes, regen, update, regenerate, onPick }: {
  job: JobDetail; scenes: Scene[]; regen: number | null
  update: (i: number, p: Partial<Scene>) => void; regenerate: (i: number, text?: string, preview?: boolean) => Promise<Scene | null>; onPick: (i: number) => void
}) {
  const [instruction, setInstruction] = useState("")
  const [edits, setEdits] = useState<AiEdit[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [done, setDone] = useState<Set<number>>(new Set())

  const run = async () => {
    setLoading(true); setEdits(null); setDone(new Set())
    try {
      const r = await api.aiPolish(job.id, scenes, instruction)
      setEdits(r.edits)
      if (!r.edits.length) toast.success("AI không thấy cần sửa gì")
    } catch (e) { toast.error("AI hậu kỳ lỗi", { description: (e as Error).message }) } finally { setLoading(false) }
  }

  const apply = async (e: AiEdit) => {
    const patch: Partial<Scene> = {}
    if (e.subtitle) patch.subtitle = e.subtitle
    if (e.exclude) patch.excluded = true
    if (Object.keys(patch).length) update(e.id, patch)
    if (e.voiceover && !e.exclude) {
      update(e.id, { voiceover: e.voiceover, ...(job.kind === "review" ? { subtitle: e.voiceover } : {}) })
      if (!(await regenerate(e.id, e.voiceover, false))) return false
    }
    setDone((d) => new Set(d).add(e.id))
    return true
  }

  const applyAll = async () => {
    setApplying(true)
    let ok = 0
    for (const e of edits ?? []) if (!done.has(e.id) && (await apply(e))) ok++
    setApplying(false)
    toast.success(`Đã áp dụng ${ok} đề xuất`)
  }

  const pending = (edits ?? []).filter((e) => !done.has(e.id))
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">AI (ChatGPT/Gemini đã đăng nhập) rà toàn bộ kịch bản: sửa lời cho tự nhiên, khớp độ dài hình, bỏ ký hiệu rác và cảnh trùng. Bạn duyệt từng đề xuất trước khi áp dụng.</p>
      <Textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={2} className="text-[13px]"
        placeholder="Yêu cầu thêm (tuỳ chọn) — VD: giọng hài hước hơn, gọi nhân vật chính là “cậu bé”…" />
      <Button onClick={run} disabled={loading || applying}>
        {loading ? <Loader2 className="animate-spin" /> : <Wand2 />} {edits ? "Rà lại" : "AI hậu kỳ tự động"}
      </Button>

      {edits && edits.length > 0 && (
        <>
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs font-medium">{edits.length} đề xuất · {pending.length} chưa áp dụng</span>
            <Button size="xs" variant="outline" disabled={!pending.length || applying || regen !== null} onClick={applyAll}>
              {applying ? <Loader2 className="animate-spin" /> : <Check />} Áp dụng tất cả
            </Button>
          </div>
          {edits.map((e) => {
            const s = scenes[e.id]
            const applied = done.has(e.id)
            return (
              <div key={e.id} className={cn("flex flex-col gap-1.5 rounded-md border border-border p-2.5", applied && "opacity-55")}>
                <div className="flex items-center gap-2">
                  <button className="text-xs font-semibold hover:text-primary" onClick={() => onPick(e.id)}>Cảnh #{e.id + 1}</button>
                  {e.exclude && <span className="rounded bg-destructive/10 px-1.5 text-[10px] text-destructive">đề xuất bỏ</span>}
                  <span className="ml-auto flex gap-1">
                    {applied ? <span className="flex items-center gap-1 text-[11px] text-success"><Check className="size-3" /> Đã áp dụng</span> : (
                      <>
                        <Button size="icon-xs" variant="ghost" title="Bỏ qua" onClick={() => setEdits(edits.filter((x) => x !== e))}><X /></Button>
                        <Button size="xs" disabled={applying || regen !== null} onClick={() => apply(e)}>
                          {regen === e.id ? <Loader2 className="animate-spin" /> : <Check />} Áp dụng
                        </Button>
                      </>
                    )}
                  </span>
                </div>
                {e.reason && <p className="text-[11px] text-muted-foreground">{e.reason}</p>}
                {e.voiceover && (
                  <div className="flex flex-col gap-1 text-[12px]">
                    <p className="text-muted-foreground line-through decoration-destructive/60">{s?.voiceover}</p>
                    <p className="text-foreground">{e.voiceover}</p>
                  </div>
                )}
                {e.subtitle && <p className="text-[11px]"><span className="text-muted-foreground">Phụ đề: </span>{e.subtitle}</p>}
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}

/* ─────────────────────────────── Danh sách ─────────────────────────────── */
function SceneList({ scenes, regen, levels, playing, onPlay, update, regenerate }: {
  scenes: Scene[]; regen: number | null; levels: Record<number, "error" | "warn">; playing: string | null
  onPlay: (url: string) => void; update: (i: number, p: Partial<Scene>) => void; regenerate: (i: number) => void
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {scenes.map((s, i) => {
        const url = s.tts_path ? mediaUrl(s.tts_path) : ""
        return (
          <div key={i} className={cn("grid grid-cols-[36px_1fr_auto] items-start gap-3 border-b border-border/60 px-4 py-2.5 last:border-0", s.excluded && "opacity-40")}>
            <Button variant={playing === url ? "default" : "outline"} size="icon-sm" disabled={!url} onClick={() => onPlay(url)} className="mt-1">
              {playing === url ? <Pause /> : <Play />}
            </Button>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 text-[10.5px] text-muted-foreground">
                {levels[i] && <AlertTriangle className={cn("size-3", levels[i] === "error" ? "text-destructive" : "text-warning")} />}
                <span className="tabular font-semibold">#{i + 1}</span>
                <span className="tabular">{fmtClock(s.clip_start)} → {fmtClock(s.clip_end)}</span>
                <span className="tabular">· {(s.tts_duration ?? 0).toFixed(1)}s</span>
                {s._tts_engine_used && <span className="rounded bg-muted px-1 uppercase">{s._tts_engine_used}</span>}
              </div>
              <Textarea value={s.voiceover} rows={1} className="min-h-9 resize-y py-2 text-[13px]" onChange={(e) => update(i, { voiceover: e.target.value })} />
            </div>
            <div className="mt-1 flex gap-1">
              <Button variant="ghost" size="icon-sm" title="Tạo lại giọng" disabled={regen !== null} onClick={() => regenerate(i)}>
                {regen === i ? <Loader2 className="animate-spin" /> : <RefreshCw />}
              </Button>
              <Button variant="ghost" size="icon-sm" title={s.excluded ? "Dùng lại" : "Bỏ câu"} onClick={() => update(i, { excluded: !s.excluded })}>
                {s.excluded ? <EyeOff /> : <Eye />}
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
