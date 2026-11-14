// Tema claro/oscuro. El cambio se anima con un círculo que crece desde donde hiciste clic.
import type { Theme } from './api'

const media = window.matchMedia('(prefers-color-scheme: dark)')
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

// Último punto donde se tocó la pantalla: de ahí nace la animación.
let origin: { x: number; y: number } | null = null
window.addEventListener('pointerdown', (e) => (origin = { x: e.clientX, y: e.clientY }), true)

export const isDark = (theme: Theme) => theme === 'dark' || (theme === 'system' && media.matches)

export function onSystemThemeChange(fn: () => void) {
  media.addEventListener('change', fn)
  return () => media.removeEventListener('change', fn)
}

export function applyTheme(dark: boolean) {
  const root = document.documentElement
  const next = dark ? 'dark' : 'light'
  const current = root.dataset.theme
  if (current === next) return
  const set = () => {
    root.dataset.theme = next
  }
  // La primera vez (al abrir) se aplica sin animación.
  if (!current || reducedMotion.matches || !document.startViewTransition) return set()

  const { x, y } = origin ?? { x: window.innerWidth - 60, y: 30 }
  origin = null
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
  const transition = document.startViewTransition(set)
  transition.ready
    .then(() => {
      root.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 560, easing: 'cubic-bezier(.65,0,.35,1)', pseudoElement: '::view-transition-new(root)' },
      )
    })
    .catch(() => {})
}
