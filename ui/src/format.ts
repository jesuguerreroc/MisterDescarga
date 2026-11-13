import type { Preset } from './api'

export const PRESETS: { id: Preset; label: string; hint: string; kind: 'video' | 'audio'; height?: number }[] = [
  { id: 'mp4_best', label: 'Mejor', hint: 'MP4 · máxima calidad', kind: 'video' },
  { id: 'mp4_1080', label: '1080p', hint: 'MP4 · Full HD', kind: 'video', height: 1080 },
  { id: 'mp4_720', label: '720p', hint: 'MP4 · HD', kind: 'video', height: 720 },
  { id: 'mp4_480', label: '480p', hint: 'MP4 · liviano', kind: 'video', height: 480 },
  { id: 'mp3_320', label: 'MP3 320', hint: 'Audio · alta calidad', kind: 'audio' },
  { id: 'mp3_192', label: 'MP3 192', hint: 'Audio · liviano', kind: 'audio' },
  { id: 'm4a', label: 'M4A', hint: 'Audio · original', kind: 'audio' },
]

export const presetLabel = (id: Preset) => {
  const p = PRESETS.find((x) => x.id === id)
  if (!p) return id
  return p.kind === 'video' ? `MP4 ${p.label}` : p.label
}

export function bytes(n: number): string {
  if (!n || n < 0) return '—'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(i >= 2 ? 1 : 0)} ${u[i]}`
}

export function duration(sec: number): string {
  if (!sec) return ''
  sec = Math.round(sec)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const pad = (x: number) => String(x).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export function eta(sec: number): string {
  if (!sec || sec < 0) return ''
  if (sec < 60) return `${Math.round(sec)} s`
  if (sec < 3600) return `${Math.floor(sec / 60)} min ${Math.round(sec % 60)} s`
  return `${Math.floor(sec / 3600)} h ${Math.floor((sec % 3600) / 60)} min`
}

export function isUrl(text: string): boolean {
  return /^https?:\/\/[^\s]+\.[^\s]+/i.test(text.trim())
}

export function dateLabel(iso: string): string {
  try {
    return new Date(iso).toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return iso
  }
}

/** "https://www.tiktok.com/@x/video/1" -> "tiktok.com" */
export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^(www|m|mobile|vm)\./, '')
  } catch {
    return url
  }
}
