import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowDownToLine, ClipboardPaste, ListVideo, X } from 'lucide-react'
import { call, type Info, type Preset, type Settings } from '../api'
import { PRESETS, duration, hostOf, isUrl } from '../format'
import { Button, Segmented, Spinner, Thumb, Toggle } from './ui'

interface Props {
  settings: Settings
  ready: boolean
  onError: (msg: string) => void
}

export function DownloadPanel({ settings, ready, onError }: Props) {
  const [url, setUrl] = useState('')
  const [info, setInfo] = useState<Info | null>(null)
  const [loading, setLoading] = useState(false)
  const [preset, setPreset] = useState<Preset>(settings.default_preset)
  const [playlist, setPlaylist] = useState(false)
  const [starting, setStarting] = useState(false)
  const [suggestion, setSuggestion] = useState('')
  const lastClip = useRef('')
  const inputRef = useRef<HTMLInputElement>(null)
  const reqId = useRef(0)

  async function lookup(target = url) {
    const clean = target.trim()
    if (!clean) return inputRef.current?.focus()
    if (!isUrl(clean)) return onError('Eso no parece un enlace. Tiene que empezar con http:// o https://')
    const id = ++reqId.current
    setUrl(clean)
    setLoading(true)
    setInfo(null)
    setSuggestion('')
    try {
      const data = await call('get_info', clean)
      if (id !== reqId.current) return
      setInfo(data)
      setPlaylist(data.is_playlist)
      setPreset((cur) => {
        const wanted = cur ?? settings.default_preset
        const isVideo = PRESETS.find((p) => p.id === wanted)?.kind === 'video'
        return !data.has_video && isVideo ? 'mp3_320' : wanted
      })
    } catch (e) {
      if (id === reqId.current) onError((e as Error).message)
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }

  // Al volver a la ventana, ofrece el enlace que esté copiado.
  useEffect(() => {
    if (!settings.watch_clipboard) return
    const check = async () => {
      try {
        const text = (await call('read_clipboard')).trim()
        if (isUrl(text) && text !== lastClip.current) {
          lastClip.current = text
          setSuggestion(text)
        }
      } catch {
        /* sin portapapeles */
      }
    }
    check()
    window.addEventListener('focus', check)
    return () => window.removeEventListener('focus', check)
  }, [settings.watch_clipboard])

  // Ctrl+V en cualquier parte de la ventana pega y busca.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) return
      const text = e.clipboardData?.getData('text')?.trim() ?? ''
      if (isUrl(text)) {
        e.preventDefault()
        lookup(text)
      }
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  })

  async function paste() {
    try {
      const text = (await call('read_clipboard')).trim()
      if (!text) return onError('No hay nada copiado.')
      lookup(text)
    } catch (e) {
      onError((e as Error).message)
    }
  }

  async function start() {
    const target = info?.url ?? url.trim()
    if (!target) return
    setStarting(true)
    try {
      await call('start_download', target, preset, playlist, info?.title ?? '', info?.thumbnail ?? '')
      setInfo(null)
      setUrl('')
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  function reset() {
    reqId.current++
    setUrl('')
    setInfo(null)
    setLoading(false)
    inputRef.current?.focus()
  }

  const tooTall = (h?: number) => !!info && !info.is_playlist && !!h && info.max_height > 0 && info.max_height < h
  const video = PRESETS.filter((p) => p.kind === 'video').map((p) => ({
    id: p.id,
    label: p.label,
    title: tooTall(p.height) ? 'Este video no tiene esa calidad' : p.hint,
    disabled: !!info && (!info.has_video || tooTall(p.height)),
  }))
  const audio = PRESETS.filter((p) => p.kind === 'audio').map((p) => ({ id: p.id, label: p.label, title: p.hint }))
  const isVideo = PRESETS.find((p) => p.id === preset)?.kind === 'video'

  return (
    <div>
      <h1 className="font-display text-[30px] leading-tight font-bold tracking-[-0.02em]">¿Qué bajamos hoy?</h1>
      <p className="mt-1 mb-5 text-ink-2">
        Pega un enlace de TikTok, YouTube, Instagram, X o donde sea. También funciona <Kbd>Ctrl</Kbd>
        <span className="mx-0.5">+</span>
        <Kbd>V</Kbd> en cualquier parte.
      </p>

      <form
        className="flex items-stretch gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          lookup()
        }}
      >
        <div className="flex min-w-0 flex-1 items-center rounded-xl border-2 border-ink bg-card pr-1.5 focus-within:shadow-[0_0_0_3px_var(--color-sun)]">
          <input
            ref={inputRef}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…"
            className="h-12 min-w-0 flex-1 bg-transparent px-4 text-[15px] outline-none focus-visible:outline-none placeholder:text-ink-3"
            autoFocus
            spellCheck={false}
          />
          {url ? (
            <button type="button" onClick={reset} title="Borrar" className="grid size-8 cursor-pointer place-items-center rounded-lg text-ink-3 hover:bg-sunk hover:text-ink">
              <X className="size-4" />
            </button>
          ) : (
            <Button type="button" variant="quiet" onClick={paste}>
              <ClipboardPaste className="size-4" /> Pegar
            </Button>
          )}
        </div>
        <Button type="submit" variant="primary" disabled={loading || !ready} className="px-5 text-[14px]">
          {loading ? <Spinner /> : null} Buscar
        </Button>
      </form>

      {suggestion && !info && !loading && suggestion !== url && (
        <div className="rise mt-3 flex items-center gap-3 rounded-xl bg-sun-soft px-4 py-2.5">
          <span className="min-w-0 flex-1 truncate">
            Copiaste un enlace de <b className="font-semibold">{hostOf(suggestion)}</b>. ¿Lo bajamos?
          </span>
          <Button variant="dark" className="py-1.5" onClick={() => lookup(suggestion)}>
            Sí
          </Button>
          <Button variant="quiet" onClick={() => setSuggestion('')}>
            No
          </Button>
        </div>
      )}

      {loading && (
        <div className="rise mt-5 flex items-center gap-4 rounded-2xl border border-line bg-card p-4">
          <div className="h-[90px] w-40 animate-pulse rounded-lg bg-sunk" />
          <div className="flex-1 space-y-2.5">
            <div className="h-4 w-2/3 animate-pulse rounded bg-sunk" />
            <div className="h-3 w-1/4 animate-pulse rounded bg-sunk" />
            <p className="pt-1 text-[13px] text-ink-3">Mirando qué hay en ese enlace…</p>
          </div>
        </div>
      )}

      {info && (
        <div className="rise mt-5 overflow-hidden rounded-2xl border border-line bg-card">
          <div className="flex gap-4 p-4">
            <div className="relative shrink-0">
              <Thumb src={info.thumbnail} audio={!info.has_video} className="h-[108px] w-[192px] rounded-lg" />
              {info.duration > 0 && (
                <span className="absolute right-1.5 bottom-1.5 rounded bg-ink/85 px-1.5 py-px text-[11px] font-semibold text-paper tabular-nums">
                  {duration(info.duration)}
                </span>
              )}
            </div>
            <div className="min-w-0 flex-1 py-0.5">
              <p className="text-[12px] font-semibold tracking-wide text-ink-3 uppercase">
                {info.site}
                {info.is_playlist && (
                  <span className="ml-2 inline-flex items-center gap-1 normal-case tracking-normal text-ink-2">
                    <ListVideo className="size-3.5" /> lista de {info.count}
                  </span>
                )}
              </p>
              <h2 className="mt-1 line-clamp-2 font-display text-[18px] leading-snug font-semibold tracking-[-0.01em]">{info.title}</h2>
              {info.uploader && <p className="mt-0.5 truncate text-ink-2">{info.uploader}</p>}
              {info.maybe_playlist && (
                <div className="mt-3">
                  <Toggle checked={playlist} onChange={setPlaylist} label="Bajar toda la lista" />
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-end justify-between gap-4 border-t border-line bg-paper/60 px-4 py-3.5">
            <div className="space-y-2">
              <Row label="Video">
                <Segmented options={video} value={isVideo ? preset : null} onChange={setPreset} />
              </Row>
              <Row label="Solo audio">
                <Segmented options={audio} value={isVideo ? null : preset} onChange={setPreset} />
              </Row>
            </div>
            <Button variant="primary" onClick={start} disabled={starting} className="px-6 py-2.5 text-[15px]">
              {starting ? <Spinner /> : <ArrowDownToLine className="size-[18px]" strokeWidth={2.5} />} Descargar
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-[70px] text-[12.5px] font-semibold text-ink-3">{label}</span>
      {children}
    </div>
  )
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line-strong border-b-2 bg-card px-1.5 py-px font-sans text-[11.5px] font-semibold text-ink">
      {children}
    </kbd>
  )
}
