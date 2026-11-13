import { AlertTriangle, Check, FolderOpen, Play, RotateCcw, Trash2, X } from 'lucide-react'
import { call, type Job } from '../api'
import { bytes, eta, presetLabel } from '../format'
import { IconButton, Thumb } from './ui'

const ACTIVE = new Set(['queued', 'downloading', 'processing'])

export function JobList({ jobs, onError, refresh }: { jobs: Job[]; onError: (m: string) => void; refresh: () => void }) {
  if (!jobs.length) return null
  const active = jobs.filter((j) => ACTIVE.has(j.status)).length
  const finished = jobs.length - active

  const act = (p: Promise<unknown>) => {
    p.then(refresh).catch((e: Error) => onError(e.message))
  }

  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="font-display text-[17px] font-semibold tracking-[-0.01em]">
          Descargas
          {active > 0 && <span className="ml-2 text-[13px] font-normal text-ink-3 font-sans">{active} en marcha</span>}
        </h3>
        {finished > 0 && (
          <button onClick={() => act(call('clear_finished'))} className="cursor-pointer text-[13px] text-ink-3 underline-offset-2 hover:text-ink hover:underline">
            Quitar terminadas
          </button>
        )}
      </div>
      <ul className="overflow-hidden rounded-2xl border border-line bg-card">
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} act={act} />
        ))}
      </ul>
    </section>
  )
}

function JobRow({ job, act }: { job: Job; act: (p: Promise<unknown>) => void }) {
  const isAudio = job.preset.startsWith('mp3') || job.preset === 'm4a'
  const running = job.status === 'downloading' || job.status === 'processing'
  const pct = Math.round(job.progress)

  let status: string
  switch (job.status) {
    case 'queued':
      status = 'Esperando turno'
      break
    case 'downloading': {
      const parts: string[] = []
      if (job.playlist && job.item_count) parts.push(`${job.item_index} de ${job.item_count}`)
      if (job.stage) parts.push(job.stage === 'audio' ? 'bajando audio' : 'bajando video')
      if (job.total) parts.push(`${bytes(job.downloaded)} de ${bytes(job.total)}`)
      if (job.speed) parts.push(`${bytes(job.speed)}/s`)
      if (job.eta) parts.push(`faltan ${eta(job.eta)}`)
      status = parts.join('  ·  ') || 'Empezando…'
      break
    }
    case 'processing':
      status = isAudio ? 'Convirtiendo el audio…' : 'Juntando video y audio…'
      break
    case 'done':
      status = job.playlist ? `Listo, ${job.files} archivos` : 'Listo'
      break
    case 'canceled':
      status = 'Cancelada'
      break
    default:
      status = job.error
  }

  return (
    <li className="rise relative border-b border-line last:border-0">
      <div className="flex items-center gap-3.5 px-3.5 py-3">
        <Thumb src={job.thumbnail} audio={isAudio} className="h-[42px] w-[74px] shrink-0 rounded-md" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate font-semibold" title={job.title}>
              {job.title}
            </p>
            <span className="shrink-0 rounded border border-line px-1.5 text-[11px] font-semibold text-ink-3">{presetLabel(job.preset)}</span>
          </div>
          {job.playlist && job.item_title && running && <p className="truncate text-[12.5px] text-ink-3">{job.item_title}</p>}
          <p
            className={`mt-0.5 flex items-center gap-1.5 truncate text-[12.5px] tabular-nums ${
              job.status === 'error' ? 'text-bad' : job.status === 'done' ? 'text-ok' : 'text-ink-3'
            }`}
            title={status}
          >
            {job.status === 'done' && <Check className="size-3.5 shrink-0" strokeWidth={3} />}
            {job.status === 'error' && <AlertTriangle className="size-3.5 shrink-0" />}
            <span className="truncate">{status}</span>
          </p>
          {job.warning && job.status === 'done' && (
            <p className="truncate text-[12px] text-warn" title={job.warning}>
              {job.warning}
            </p>
          )}
        </div>

        {running && <span className="w-10 shrink-0 text-right font-display text-[15px] font-semibold tabular-nums">{pct}%</span>}

        <div className="flex shrink-0 items-center">
          {job.status === 'done' && !job.playlist && job.filepath && (
            <IconButton title="Abrir" onClick={() => act(call('open_path', job.filepath, false))}>
              <Play className="size-4" />
            </IconButton>
          )}
          {job.status === 'done' && (
            <IconButton
              title="Ver en la carpeta"
              onClick={() => act(job.filepath ? call('open_path', job.filepath, !job.playlist) : call('open_download_dir'))}
            >
              <FolderOpen className="size-4" />
            </IconButton>
          )}
          {(job.status === 'error' || job.status === 'canceled') && (
            <IconButton title="Reintentar" onClick={() => act(call('retry', job.id))}>
              <RotateCcw className="size-4" />
            </IconButton>
          )}
          {ACTIVE.has(job.status) ? (
            <IconButton title="Cancelar" onClick={() => act(call('cancel', job.id))}>
              <X className="size-4" />
            </IconButton>
          ) : (
            <IconButton title="Quitar de la lista" onClick={() => act(call('remove', job.id))}>
              <Trash2 className="size-4" />
            </IconButton>
          )}
        </div>
      </div>

      {(running || job.status === 'queued') && (
        <div className="absolute inset-x-0 bottom-0 h-[3px] bg-sunk">
          <div
            className={`h-full transition-[width] duration-300 ${job.status === 'processing' ? 'stripes' : 'bg-ink'}`}
            style={{ width: `${job.status === 'queued' ? 0 : job.status === 'processing' ? 100 : Math.max(pct, 1)}%` }}
          />
        </div>
      )}
    </li>
  )
}
