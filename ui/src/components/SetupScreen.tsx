import { AlertTriangle, Check } from 'lucide-react'
import { bytes } from '../format'
import type { SetupState } from '../setup'
import { Button, Penguin, Spinner } from './ui'

const ORDER = ['ytdlp', 'ffmpeg', 'deno']

export function SetupScreen({ state, onRetry, firstRun }: { state: SetupState; onRetry: () => void; firstRun: boolean }) {
  const keys = ORDER.filter((k) => state.items[k]).concat(Object.keys(state.items).filter((k) => !ORDER.includes(k)))
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-paper p-6">
      <div className="rise w-full max-w-[420px]">
        <div className="mb-6 flex flex-col items-center text-center">
          <Penguin size={92} className={state.error ? '' : 'waddle'} />
          <h1 className="mt-4 font-display text-[24px] font-bold tracking-[-0.02em]">{firstRun ? '¡Hola! Un momento…' : 'Instalando…'}</h1>
          <p className="mt-1 text-ink-2">
            {firstRun ? 'Estoy bajando lo que necesito para descargar. Solo pasa la primera vez.' : 'Ya casi.'}
          </p>
        </div>

        <ul className="rounded-2xl border border-line bg-card">
          {keys.length === 0 && !state.error && (
            <li className="flex items-center gap-2 px-4 py-3 text-ink-3">
              <Spinner className="size-3.5" /> Conectando…
            </li>
          )}
          {keys.map((k) => {
            const it = state.items[k]
            const done = it.pct >= 100
            return (
              <li key={k} className="border-b border-line px-4 py-3 last:border-0">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 font-semibold">
                    {done ? <Check className="size-4 text-ok" strokeWidth={3} /> : <Spinner className="size-3.5" />}
                    {it.name}
                  </span>
                  <span className="text-[12.5px] text-ink-3 tabular-nums">
                    {done ? 'Listo' : it.total ? `${bytes(it.done)} de ${bytes(it.total)}` : `${Math.round(it.pct)}%`}
                  </span>
                </div>
                <div className="h-[3px] overflow-hidden rounded-full bg-sunk">
                  <div className={`h-full transition-[width] duration-300 ${done ? 'bg-ok' : 'bg-ink'}`} style={{ width: `${Math.max(1, it.pct)}%` }} />
                </div>
              </li>
            )
          })}
        </ul>

        {state.error && (
          <div className="mt-4 rounded-xl bg-bad/10 p-4">
            <p className="mb-3 flex gap-2 text-ink">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" />
              <span>{state.error}. Revisa tu conexión a internet.</span>
            </p>
            <Button variant="dark" onClick={onRetry}>
              Intentar de nuevo
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
