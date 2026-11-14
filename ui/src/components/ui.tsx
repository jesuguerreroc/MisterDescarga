import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { useState } from 'react'
import { Film, Music } from 'lucide-react'

/* ---------- El pingüino ---------- */

const BODY = 'M128 16 C192 16 216 72 216 140 C216 206 180 240 128 240 C76 240 40 206 40 140 C40 72 64 16 128 16 Z'
const FACE =
  'M128 74 C112 58 70 60 68 100 C66 128 76 140 76 160 C76 200 98 222 128 222 C158 222 180 200 180 160 C180 140 190 128 188 100 C186 60 144 58 128 74 Z'
const GLASSES = 'M54 88 H202 V104 Q202 136 166 136 Q136 136 134 108 H122 Q120 136 90 136 Q54 136 54 104 Z'
const GLINT = 'M72 96 H84 L74 116 H62 Z M146 96 H158 L148 116 H136 Z'
const BEAK = 'M106 146 H150 Q152 146 150 149 L131 173 Q128 177 125 173 L106 149 Q104 146 106 146 Z'

function PenguinShapes() {
  return (
    <>
      <path fill="#17160f" d={BODY} className="penguin-body" />
      <path fill="#fffefa" d={FACE} />
      <path fill="#17160f" d={GLASSES} />
      <path fill="#fffefa" d={GLINT} />
      <path fill="#ff8a3d" d={BEAK} />
    </>
  )
}

/** Icono de la app: pingüino con gafas sobre amarillo sol. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 256 256" aria-hidden>
      <rect width="256" height="256" rx="60" fill="#ffd23f" />
      <g transform="translate(128 130) scale(0.8) translate(-128 -128)">
        <PenguinShapes />
      </g>
    </svg>
  )
}

/** El pingüino solo, para estados vacíos y bienvenida. */
export function Penguin({ size = 96, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 256 256" aria-hidden className={`penguin-solo ${className}`}>
      <ellipse cx="128" cy="244" rx="70" ry="8" style={{ fill: 'var(--color-ink)' }} opacity="0.08" />
      <PenguinShapes />
    </svg>
  )
}

/* ---------- Controles ---------- */

type Variant = 'primary' | 'dark' | 'outline' | 'quiet' | 'danger'

export function Button({
  variant = 'outline',
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-[10px] text-[13.5px] font-semibold cursor-pointer select-none disabled:opacity-40 disabled:cursor-not-allowed'
  const styles: Record<Variant, string> = {
    primary: 'press bg-sun text-on-sun border-2 border-on-sun px-4 py-2 hover:brightness-105',
    dark: 'bg-ink text-paper px-4 py-2 hover:opacity-90',
    outline: 'border border-line-strong bg-card text-ink px-3 py-1.5 hover:border-ink',
    quiet: 'text-ink-2 px-2.5 py-1.5 hover:text-ink hover:bg-sunk',
    danger: 'text-bad px-2.5 py-1.5 hover:bg-bad/10',
  }
  return (
    <button className={`${base} ${styles[variant]} ${className}`} {...rest}>
      {children}
    </button>
  )
}

export function IconButton({ title, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { title: string }) {
  return (
    <button
      title={title}
      aria-label={title}
      className="grid size-8 cursor-pointer place-items-center rounded-lg text-ink-2 hover:bg-sunk hover:text-ink disabled:opacity-40"
      {...rest}
    >
      {children}
    </button>
  )
}

/** Grupo de opciones pegadas (una elegida). */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string; title?: string; disabled?: boolean }[]
  value: T | null
  onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex rounded-[10px] border border-line-strong bg-card p-0.5">
      {options.map((o) => {
        const active = value === o.id
        return (
          <button
            key={o.id}
            type="button"
            disabled={o.disabled}
            title={o.title}
            onClick={() => onChange(o.id)}
            className={`rounded-[8px] px-3 py-1.5 text-[13px] font-semibold tabular-nums cursor-pointer disabled:cursor-not-allowed disabled:text-line-strong ${
              active ? 'bg-ink text-paper' : 'text-ink-2 hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export function Thumb({ src, audio, className = '' }: { src: string; audio?: boolean; className?: string }) {
  const [broken, setBroken] = useState(false)
  if (!src || broken) {
    return (
      <div className={`grid place-items-center bg-sunk text-ink-3 ${className}`}>
        {audio ? <Music className="size-5" /> : <Film className="size-5" />}
      </div>
    )
  }
  return (
    <img
      src={src}
      alt=""
      referrerPolicy="no-referrer"
      onError={() => setBroken(true)}
      className={`bg-sunk object-cover ${className}`}
      draggable={false}
    />
  )
}

export function Spinner({ className = 'size-4' }: { className?: string }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2.5 text-[13.5px] text-ink-2">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-[22px] w-[38px] shrink-0 cursor-pointer rounded-full border-2 border-ink transition-colors ${
          checked ? 'bg-sun' : 'bg-card'
        }`}
      >
        <span
          className={`absolute top-[2px] size-[14px] rounded-full transition-all ${checked ? 'left-[18px] bg-on-sun' : 'left-[2px] bg-ink'}`}
        />
      </button>
      {label}
    </label>
  )
}
