// Puente con Python (pywebview). En el navegador (npm run dev) usa un mock para poder diseñar la UI.

export type Preset = 'mp4_best' | 'mp4_1080' | 'mp4_720' | 'mp4_480' | 'mp3_320' | 'mp3_192' | 'm4a'
export type JobStatus = 'queued' | 'downloading' | 'processing' | 'done' | 'error' | 'canceled'
export type Theme = 'system' | 'light' | 'dark'

export interface Settings {
  download_dir: string
  default_preset: Preset
  max_concurrent: number
  cookies_browser: string
  watch_clipboard: boolean
  notify_done: boolean
  auto_update_ytdlp: boolean
  theme: Theme
}

export interface Info {
  url: string
  title: string
  uploader: string
  duration: number
  thumbnail: string
  site: string
  is_playlist: boolean
  count: number
  maybe_playlist: boolean
  has_video: boolean
  max_height: number
  entries: string[]
}

export interface Job {
  id: string
  url: string
  preset: Preset
  playlist: boolean
  title: string
  thumbnail: string
  status: JobStatus
  progress: number
  speed: number
  eta: number
  downloaded: number
  total: number
  stage: string
  item_index: number
  item_count: number
  item_title: string
  filepath: string
  folder: string
  files: number
  error: string
  warning: string
  created: number
  resumed: boolean
}

export interface HistoryItem {
  id: string
  title: string
  url: string
  preset: Preset
  filepath: string
  folder: string
  thumbnail: string
  playlist: boolean
  files: number
  date: string
}

export interface AppState {
  version: string
  settings: Settings
  tools_ready: boolean
  missing_tools: string[]
  ffmpeg: FfmpegState
  jobs: Job[]
  ytdlp_updating: boolean
  app_update: AppUpdate | null
}

export interface AppUpdate {
  current: string
  latest: string
  newer: boolean
  url: string
}

export type AppEvent =
  | { type: 'ytdlp'; status: 'updating' }
  | { type: 'ytdlp'; status: 'done'; version: string; changed: boolean }
  | { type: 'app-update'; update: AppUpdate }

export type FfmpegState = 'ok' | 'blocked' | 'missing'

export interface ToolsInfo {
  ytdlp: string
  bin_dir: string
  ffmpeg: FfmpegState
  ffmpeg_dir: string
}

export interface SetupEvent {
  id?: string
  name?: string
  pct?: number
  done?: number
  total?: number
  finished?: boolean
  ffmpeg?: FfmpegState
  error?: string
}

type Result<T> = { ok: true; data: T } | { ok: false; error: string }

interface PyApi {
  get_state(): Promise<Result<AppState>>
  save_settings(data: Partial<Settings>): Promise<Result<Settings>>
  choose_folder(): Promise<Result<Settings | null>>
  read_clipboard(): Promise<Result<string>>
  setup_tools(): Promise<Result<string>>
  tools_info(): Promise<Result<ToolsInfo>>
  ffmpeg_state(): Promise<Result<{ ffmpeg: FfmpegState; ffmpeg_dir: string }>>
  reinstall_ffmpeg(): Promise<Result<string>>
  update_ytdlp(): Promise<Result<{ output: string; version: string }>>
  apply_theme(dark: boolean): Promise<Result<null>>
  check_app_update(): Promise<Result<AppUpdate>>
  open_url(url: string): Promise<Result<null>>
  get_info(url: string): Promise<Result<Info>>
  start_download(url: string, preset: Preset, playlist: boolean, title: string, thumbnail: string): Promise<Result<Job>>
  cancel(id: string): Promise<Result<null>>
  retry(id: string): Promise<Result<Job | null>>
  remove(id: string): Promise<Result<null>>
  clear_finished(): Promise<Result<null>>
  open_path(path: string, select: boolean): Promise<Result<null>>
  open_download_dir(): Promise<Result<null>>
  get_history(): Promise<Result<HistoryItem[]>>
  clear_history(): Promise<Result<null>>
}

declare global {
  interface Window {
    pywebview?: { api: PyApi }
    __mdJob?: (job: Job) => void
    __mdSetup?: (ev: SetupEvent) => void
    __mdEvent?: (ev: AppEvent) => void
  }
}

let resolved: PyApi | null = null

function waitForPy(): Promise<PyApi> {
  if (resolved) return Promise.resolve(resolved)
  return new Promise((resolve) => {
    const done = () => {
      resolved = window.pywebview?.api ?? createMock()
      resolve(resolved)
    }
    if (window.pywebview?.api) return done()
    window.addEventListener('pywebviewready', done, { once: true })
    // Fuera de pywebview (navegador normal) caemos al mock tras un momento.
    setTimeout(() => !resolved && done(), 1200)
  })
}

/** Llama a un método de Python y lanza Error con el mensaje si falla. */
export async function call<K extends keyof PyApi>(
  name: K,
  ...args: Parameters<PyApi[K]>
): Promise<Awaited<ReturnType<PyApi[K]>> extends Result<infer T> ? T : never> {
  const api = await waitForPy()
  const fn = api[name] as (...a: unknown[]) => Promise<Result<unknown>>
  const res = await fn(...args)
  if (!res.ok) throw new Error(res.error)
  return res.data as never
}

export const isMock = () => resolved !== null && !window.pywebview?.api

// ---------------------------------------------------------------------------
// Mock para desarrollo en navegador
function createMock(): PyApi {
  const ok = <T,>(data: T): Promise<Result<T>> => Promise.resolve({ ok: true, data })
  let settings: Settings = {
    download_dir: 'C:\\Users\\tu\\Downloads\\MisterDescarga',
    default_preset: 'mp4_best',
    max_concurrent: 2,
    cookies_browser: '',
    watch_clipboard: true,
    notify_done: true,
    auto_update_ytdlp: true,
    theme: 'system',
  }
  const jobs: Job[] = []
  const fakeJob = (url: string, preset: Preset, playlist: boolean, title: string, thumbnail: string): Job => ({
    id: Math.random().toString(36).slice(2, 12), url, preset, playlist, title: title || url, thumbnail,
    status: 'downloading', progress: 0, speed: 0, eta: 0, downloaded: 0, total: 50e6, stage: '',
    item_index: 0, item_count: 0, item_title: '', filepath: '', folder: '', files: 0, error: '', warning: '',
    created: Date.now() / 1000, resumed: false,
  })
  return {
    get_state: () =>
      ok({ version: 'dev', settings, tools_ready: true, missing_tools: [], ffmpeg: 'ok', jobs, ytdlp_updating: false, app_update: null }),
    save_settings: (d) => ok((settings = { ...settings, ...d })),
    choose_folder: () => ok(settings),
    read_clipboard: () => ok(''),
    setup_tools: () => ok('started'),
    tools_info: () => ok({ ytdlp: '2026.11.01', bin_dir: 'C:\\bin', ffmpeg: 'ok', ffmpeg_dir: 'C:\\bin' }),
    ffmpeg_state: () => ok({ ffmpeg: 'ok', ffmpeg_dir: '' }),
    reinstall_ffmpeg: () => ok('started'),
    update_ytdlp: () => ok({ output: 'yt-dlp is up to date', version: '2026.11.01' }),
    apply_theme: () => ok(null),
    check_app_update: () => ok({ current: 'dev', latest: '1.1.0', newer: true, url: 'https://github.com/' }),
    open_url: () => ok(null),
    get_info: (url) =>
      new Promise((r) =>
        setTimeout(() => r({
          ok: true,
          data: {
            url, title: 'Video de ejemplo con un título bastante largo para ver cómo se corta', uploader: 'Canal de prueba',
            duration: 245, thumbnail: '', site: 'Youtube', is_playlist: false, count: 0,
            maybe_playlist: url.includes('list='), has_video: true, max_height: 1080, entries: [],
          },
        }), 700),
      ),
    start_download: (url, preset, playlist, title, thumbnail) => {
      const job = fakeJob(url, preset, playlist, title, thumbnail)
      jobs.unshift(job)
      const tick = setInterval(() => {
        job.progress = Math.min(100, job.progress + Math.random() * 9)
        job.speed = 2e6 + Math.random() * 3e6
        job.eta = Math.max(0, (100 - job.progress) / 5)
        if (job.progress >= 100) {
          Object.assign(job, { status: 'done', filepath: 'C:\\x\\video.mp4', folder: 'C:\\x', files: 1 })
          clearInterval(tick)
        }
        window.__mdJob?.({ ...job })
      }, 400)
      return ok(job)
    },
    cancel: (id) => {
      const j = jobs.find((x) => x.id === id)
      if (j) { j.status = 'canceled'; window.__mdJob?.({ ...j }) }
      return ok(null)
    },
    retry: () => ok(null),
    remove: () => ok(null),
    clear_finished: () => ok(null),
    open_path: () => ok(null),
    open_download_dir: () => ok(null),
    get_history: () => ok([]),
    clear_history: () => ok(null),
  }
}
