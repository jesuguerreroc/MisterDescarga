import { useEffect, useState, type ReactNode } from 'react'
import { Check, RefreshCw } from 'lucide-react'
import { call, type AppUpdate, type Preset, type Settings, type Theme, type ToolsInfo } from '../api'
import { PRESETS, presetLabel } from '../format'
import { Button, Segmented, Spinner, Toggle } from './ui'

interface Props {
  settings: Settings
  version: string
  onChange: (s: Settings) => void
  onError: (m: string) => void
  onReinstallFfmpeg: () => void
  onAppUpdate: (u: AppUpdate | null) => void
}

const BROWSERS = [
  { id: '', label: 'No usar' },
  { id: 'firefox', label: 'Firefox (el que mejor funciona)' },
  { id: 'chrome', label: 'Chrome' },
  { id: 'edge', label: 'Edge' },
  { id: 'brave', label: 'Brave' },
  { id: 'opera', label: 'Opera' },
  { id: 'vivaldi', label: 'Vivaldi' },
]

const selectCls = 'rounded-[10px] border border-line-strong bg-card px-3 py-2 outline-none hover:border-ink focus:border-ink cursor-pointer'

const THEMES: { id: Theme; label: string }[] = [
  { id: 'light', label: 'Claro' },
  { id: 'dark', label: 'Oscuro' },
  { id: 'system', label: 'Como Windows' },
]

export function SettingsPanel({ settings, version, onChange, onError, onReinstallFfmpeg, onAppUpdate }: Props) {
  const [tools, setTools] = useState<ToolsInfo | null>(null)
  const [updating, setUpdating] = useState(false)
  const [updateOut, setUpdateOut] = useState('')
  const [checking, setChecking] = useState(false)
  const [appCheck, setAppCheck] = useState<AppUpdate | null>(null)

  useEffect(() => {
    call('tools_info').then(setTools).catch(() => {})
  }, [])

  const save = async (patch: Partial<Settings>) => {
    try {
      onChange(await call('save_settings', patch))
    } catch (e) {
      onError((e as Error).message)
    }
  }

  const chooseFolder = async () => {
    try {
      const s = await call('choose_folder')
      if (s) onChange(s)
    } catch (e) {
      onError((e as Error).message)
    }
  }

  const update = async () => {
    setUpdating(true)
    setUpdateOut('')
    try {
      const r = await call('update_ytdlp')
      setUpdateOut(r.output)
      setTools((t) => (t ? { ...t, ytdlp: r.version } : t))
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setUpdating(false)
    }
  }

  const checkApp = async () => {
    setChecking(true)
    try {
      const r = await call('check_app_update')
      setAppCheck(r)
      onAppUpdate(r.newer ? r : null)
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setChecking(false)
    }
  }

  const recheck = async () => {
    const r = await call('ffmpeg_state')
    setTools((t) => (t ? { ...t, ...r } : t))
  }

  return (
    <div>
      <h1 className="mb-5 font-display text-[26px] leading-tight font-bold tracking-[-0.02em]">Ajustes</h1>

      <Group title="Apariencia">
        <Item label="Tema" hint="«Como Windows» sigue el modo claro u oscuro del sistema.">
          <Segmented options={THEMES} value={settings.theme} onChange={(v) => save({ theme: v })} />
        </Item>
      </Group>

      <Group title="Descargas">
        <Item label="Guardar en" hint={settings.download_dir}>
          <div className="flex gap-1.5">
            <Button onClick={chooseFolder}>Cambiar…</Button>
            <Button variant="quiet" onClick={() => call('open_download_dir').catch((e: Error) => onError(e.message))}>
              Abrir
            </Button>
          </div>
        </Item>
        <Item label="Formato de siempre" hint="El que aparece elegido al buscar un enlace.">
          <select value={settings.default_preset} onChange={(e) => save({ default_preset: e.target.value as Preset })} className={selectCls}>
            {PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {presetLabel(p.id)} · {p.hint.split(' · ')[1]}
              </option>
            ))}
          </select>
        </Item>
        <Item label="Descargas a la vez" hint="Más a la vez no siempre es más rápido.">
          <Segmented
            options={(['1', '2', '3', '4'] as const).map((n) => ({ id: n, label: n }))}
            value={String(settings.max_concurrent) as '1' | '2' | '3' | '4'}
            onChange={(v) => save({ max_concurrent: Number(v) })}
          />
        </Item>
        <Item label="Detectar enlaces copiados" hint="Al volver a la ventana, te ofrece bajar lo que copiaste.">
          <Toggle checked={settings.watch_clipboard} onChange={(v) => save({ watch_clipboard: v })} />
        </Item>
        <Item label="Avisarme al terminar" hint="Muestra una notificación de Windows si estás en otra ventana.">
          <Toggle checked={settings.notify_done} onChange={(v) => save({ notify_done: v })} />
        </Item>
      </Group>

      <Group title="Videos que piden iniciar sesión">
        <Item
          label="Usar mi sesión del navegador"
          hint="Para Instagram, videos con restricción de edad o privados. Chrome y Edge a veces no dejan leerla si están abiertos."
        >
          <select value={settings.cookies_browser} onChange={(e) => save({ cookies_browser: e.target.value })} className={selectCls}>
            {BROWSERS.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}
              </option>
            ))}
          </select>
        </Item>
      </Group>

      <Group title="Herramientas">
        <Item label="Actualizar yt-dlp solo" hint="Lo revisa una vez al día al abrir el programa. Así los sitios siguen funcionando.">
          <Toggle checked={settings.auto_update_ytdlp} onChange={(v) => save({ auto_update_ytdlp: v })} />
        </Item>
        <Item label="yt-dlp" hint={`Versión ${tools?.ytdlp || '—'}. Si un sitio deja de funcionar, actualízalo ahora.`}>
          <Button onClick={update} disabled={updating}>
            {updating ? <Spinner className="size-3.5" /> : <RefreshCw className="size-3.5" />} Actualizar
          </Button>
        </Item>
        {updateOut && (
          <pre className="mx-4 mb-3 max-h-28 overflow-auto rounded-lg bg-sunk p-3 text-[11.5px] whitespace-pre-wrap text-ink-2">{updateOut}</pre>
        )}
        <Item
          label="FFmpeg"
          hint={
            tools?.ffmpeg === 'ok'
              ? 'Une video con audio y convierte a MP3.'
              : tools?.ffmpeg === 'blocked'
                ? 'Windows lo bloqueó. Sin él se baja en calidad limitada y sin MP3.'
                : 'No está. Sin él se baja en calidad limitada y sin MP3.'
          }
        >
          {tools?.ffmpeg === 'ok' ? (
            <span className="inline-flex items-center gap-1.5 font-semibold text-ok">
              <Check className="size-4" strokeWidth={3} /> Funcionando
            </span>
          ) : (
            <div className="flex gap-1.5">
              <Button onClick={onReinstallFfmpeg}>Reinstalar</Button>
              <Button variant="quiet" onClick={recheck}>
                Comprobar
              </Button>
            </div>
          )}
        </Item>
        {tools && tools.ffmpeg !== 'ok' && (
          <p className="mx-4 mb-3 rounded-lg bg-sun-soft p-3 text-[13px] leading-relaxed text-ink-2">
            Si «Reinstalar» no lo arregla, instálalo aparte: abre una terminal, escribe
            <code className="mx-1 rounded bg-card px-1.5 py-0.5 font-mono text-ink">winget install Gyan.FFmpeg</code>y luego pulsa «Comprobar».
          </p>
        )}
      </Group>

      <Group title="MisterDescarga">
        <Item
          label={`Versión ${version}`}
          hint={
            appCheck
              ? appCheck.newer
                ? `Hay una versión nueva: ${appCheck.latest}.`
                : 'Tienes la última versión.'
              : 'Al abrir el programa revisa si salió una versión nueva.'
          }
        >
          {appCheck?.newer ? (
            <Button variant="primary" onClick={() => call('open_url', appCheck.url).catch((e: Error) => onError(e.message))}>
              Descargar {appCheck.latest}
            </Button>
          ) : (
            <Button onClick={checkApp} disabled={checking}>
              {checking ? <Spinner className="size-3.5" /> : <RefreshCw className="size-3.5" />} Buscar actualizaciones
            </Button>
          )}
        </Item>
      </Group>

      <p className="mt-6 text-center text-[12.5px] text-ink-3">
        Hecho con yt-dlp y FFmpeg. Úsalo solo con contenido que tengas derecho a bajar.
      </p>
    </div>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-5">
      <h2 className="mb-2 text-[12.5px] font-semibold tracking-wide text-ink-3 uppercase">{title}</h2>
      <div className="rounded-2xl border border-line bg-card">{children}</div>
    </section>
  )
}

function Item({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-line px-4 py-3 last:border-0">
      <div className="min-w-0">
        <p className="font-semibold">{label}</p>
        {hint && (
          <p className="truncate text-[12.5px] text-ink-3" title={hint}>
            {hint}
          </p>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}
