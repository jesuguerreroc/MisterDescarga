import type { SetupEvent } from './api'

export interface SetupState {
  items: Record<string, { name: string; pct: number; done: number; total: number }>
  error: string
}

export function reduceSetup(state: SetupState, ev: SetupEvent): SetupState {
  if (ev.error) return { ...state, error: ev.error }
  if (!ev.id) return state
  return {
    error: '',
    items: {
      ...state.items,
      [ev.id]: { name: ev.name ?? ev.id, pct: ev.pct ?? 0, done: ev.done ?? 0, total: ev.total ?? 0 },
    },
  }
}
