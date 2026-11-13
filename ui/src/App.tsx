import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { FolderOpen, X } from 'lucide-react'
import { call, type AppState, type Job, type Settings } from './api'
import { DownloadPanel } from './components/DownloadPanel'
import { HistoryPanel } from './components/HistoryPanel'
import { JobList } from './components/JobList'
import { SettingsPanel } from './components/SettingsPanel'
import { SetupScreen } from './components/SetupScreen'
import { Logo, Penguin, Spinner } from './components/ui'
import { reduceSetup, type SetupState } from './setup'

type Tab = 'download' | 'history' | 'settings'

export default function App() {
  const [state, setState] = useState<AppState | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [tab, setTab] = useState<Tab>('download')
  const [toast, setToast] = useState('')
  const [setup, setSetup] = useState<{ open: boolean; firstRun: boolean; s: SetupState }>({
    open: false,
    firstRun: false,
    s: { items: {}, error: '' },
  })
  const toastTimer = useRef<number | undefined>(undefined)

  const showError = useCallback((msg: string) => {
    setToast(msg)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(''), 7000)
  }, [])

  const refresh = useCallback(async () => {
    const s = await call('get_state')
    setState(s)
    setJobs(s.jobs.slice().reverse())
    return s
  }, [])

  const startSetup = useCallback(async (firstRun: boolean, reinstallFfmpeg = false) => {
    setSetup({ open: true, firstRun, s: { items: {}, error: '' } })
    try {
      await call(reinstallFfmpeg ? 'reinstall_ffmpeg' : 'setup_tools')
    } catch (e) {
      setSetup((cur) => ({ ...cur, s: { ...cur.s, error: (e as Error).message } }))
    }
  }, [])

  useEffect(() => {
    window.__mdJob = (job) =>
      setJobs((prev) => {
        const i = prev.findIndex((j) => j.id === job.id)
        if (i === -1) return [job, ...prev]
        const next = prev.slice()
        next[i] = job
        return next
      })
    window.__mdSetup = (ev) => {
      if (ev.finished) {
        setSetup((cur) => ({ ...cur, open: false }))
        refresh()
        if (ev.ffmpeg && ev.ffmpeg !== 'ok') {
          showError('FFmpeg no funciona en este equipo: se bajará en calidad limitada. Mira Ajustes → Herramientas.')
        }
        return
      }
      setSetup((cur) => ({ ...cur, s: reduceSetup(cur.s, ev) }))
    }
    refresh()
      .then((s) => {
        if (!s.tools_ready) startSetup(true)
      })
      .catch((e: Error) => showError(e.message))
    return () => {
      window.__mdJob = undefined
      window.__mdSetup = undefined
    }
  }, [refresh, startSetup, showError])

  if (!state) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner className="size-5" />
      </div>
    )
  }

  const setSettings = (s: Settings) => setState({ ...state, settings: s })
  const active = jobs.filter((j) => j.status === 'downloading' || j.status === 'processing' || j.status === 'queued').length

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-6 border-b border-line px-7 pt-3">
        <div className="flex items-center gap-2.5 pb-3">
          <Logo size={30} />
          <span className="font-display text-[19px] font-bold tracking-[-0.03em]">MisterDescarga</span>
        </div>
        <nav className="flex gap-5 self-stretch">
          <TabButton active={tab === 'download'} onClick={() => setTab('download')}>
            Descargar
            {active > 0 && <span className="ml-1.5 rounded-full bg-sun px-1.5 text-[11px] font-bold text-ink tabular-nums">{active}</span>}
          </TabButton>
          <TabButton active={tab === 'history'} onClick={() => setTab('history')}>
            Historial
          </TabButton>
          <TabButton active={tab === 'settings'} onClick={() => setTab('settings')}>
            Ajustes
          </TabButton>
        </nav>
        <button
          onClick={() => call('open_download_dir').catch((e: Error) => showError(e.message))}
          className="mb-3 ml-auto inline-flex cursor-pointer items-center gap-2 rounded-[10px] px-2.5 py-1.5 font-semibold text-ink-2 hover:bg-sunk hover:text-ink"
          title={state.settings.download_dir}
        >
          <FolderOpen className="size-4" /> Mis descargas
        </button>
      </header>

      {state.ffmpeg !== 'ok' && state.tools_ready && tab === 'download' && (
        <button onClick={() => setTab('settings')} className="cursor-pointer bg-sun-soft px-7 py-2 text-left text-[13px] text-ink">
          <b>Ojo:</b> FFmpeg no está funcionando, así que la calidad será limitada y no habrá MP3. <u>Ver cómo arreglarlo</u>
        </button>
      )}

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[760px] px-7 pt-8 pb-10">
          {tab === 'download' && (
            <>
              <DownloadPanel settings={state.settings} ready={state.tools_ready} onError={showError} />
              <div className="mt-9">
                {jobs.length ? (
                  <JobList jobs={jobs} onError={showError} refresh={refresh} />
                ) : (
                  <div className="flex items-center gap-4 rounded-2xl border border-dashed border-line-strong px-5 py-5">
                    <Penguin size={56} />
                    <div>
                      <p className="font-semibold">Aquí van a aparecer tus descargas.</p>
                      <p className="text-[13px] text-ink-2">Truco: copia un enlace en el navegador y vuelve; lo detecto solo.</p>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
          {tab === 'history' && <HistoryPanel onError={showError} />}
          {tab === 'settings' && (
            <SettingsPanel
              settings={state.settings}
              version={state.version}
              onChange={setSettings}
              onError={showError}
              onReinstallFfmpeg={() => startSetup(false, true)}
            />
          )}
        </div>
      </main>

      {toast && (
        <div className="rise fixed bottom-5 left-1/2 z-40 flex max-w-[86%] -translate-x-1/2 items-start gap-3 rounded-xl bg-ink px-4 py-3 text-paper shadow-[0_10px_30px_-10px_rgba(0,0,0,.5)]">
          <span className="mt-[3px] size-2 shrink-0 rounded-full bg-beak" />
          <span>{toast}</span>
          <button onClick={() => setToast('')} className="cursor-pointer text-paper/60 hover:text-paper" title="Cerrar">
            <X className="size-4" />
          </button>
        </div>
      )}

      {setup.open && <SetupScreen state={setup.s} firstRun={setup.firstRun} onRetry={() => startSetup(setup.firstRun)} />}
    </div>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`relative inline-flex cursor-pointer items-center pb-3 font-semibold ${active ? 'text-ink' : 'text-ink-3 hover:text-ink'}`}
    >
      {children}
      {active && <span className="absolute inset-x-0 -bottom-px h-[3px] rounded-t bg-ink" />}
    </button>
  )
}
