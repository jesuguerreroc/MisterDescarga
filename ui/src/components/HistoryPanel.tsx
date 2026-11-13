import { useEffect, useState } from 'react'
import { FolderOpen, Play, Search } from 'lucide-react'
import { call, type HistoryItem } from '../api'
import { dateLabel, presetLabel } from '../format'
import { Button, IconButton, Penguin, Thumb } from './ui'

export function HistoryPanel({ onError }: { onError: (m: string) => void }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    call('get_history').then(setItems).catch((e: Error) => onError(e.message))
  }, [onError])

  const open = (path: string, select: boolean) => call('open_path', path, select).catch((e: Error) => onError(e.message))

  const clear = async () => {
    if (!confirm('¿Borrar el historial? Los archivos descargados no se tocan.')) return
    await call('clear_history')
    setItems([])
  }

  if (items === null) return null

  if (!items.length) {
    return (
      <div className="flex flex-col items-center py-16 text-center">
        <Penguin size={88} />
        <p className="mt-4 font-display text-[18px] font-semibold">Nada por aquí todavía</p>
        <p className="text-ink-2">Lo que descargues va a quedar anotado en esta lista.</p>
      </div>
    )
  }

  const filtered = q ? items.filter((i) => i.title.toLowerCase().includes(q.toLowerCase())) : items

  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-4">
        <h1 className="font-display text-[26px] leading-tight font-bold tracking-[-0.02em]">Historial</h1>
        <Button variant="danger" onClick={clear}>
          Borrar historial
        </Button>
      </div>
      <div className="mb-3 flex items-center gap-2 rounded-xl border border-line-strong bg-card px-3 focus-within:border-ink">
        <Search className="size-4 text-ink-3" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por nombre"
          className="h-10 flex-1 bg-transparent outline-none placeholder:text-ink-3"
        />
      </div>

      <ul className="overflow-hidden rounded-2xl border border-line bg-card">
        {filtered.map((item) => {
          const isAudio = item.preset.startsWith('mp3') || item.preset === 'm4a'
          return (
            <li key={item.id + item.date} className="flex items-center gap-3.5 border-b border-line px-3.5 py-2.5 last:border-0">
              <Thumb src={item.thumbnail} audio={isAudio} className="h-[38px] w-[66px] shrink-0 rounded-md" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold" title={item.title}>
                  {item.title}
                </p>
                <p className="text-[12.5px] text-ink-3">
                  {presetLabel(item.preset)}
                  {item.playlist && ` · lista de ${item.files}`} · {dateLabel(item.date)}
                </p>
              </div>
              {!item.playlist && item.filepath && (
                <IconButton title="Abrir" onClick={() => open(item.filepath, false)}>
                  <Play className="size-4" />
                </IconButton>
              )}
              <IconButton title="Ver en la carpeta" onClick={() => open(item.filepath || item.folder, !item.playlist)}>
                <FolderOpen className="size-4" />
              </IconButton>
            </li>
          )
        })}
      </ul>
      {!filtered.length && <p className="py-10 text-center text-ink-3">No encontré nada con ese nombre.</p>}
    </div>
  )
}
