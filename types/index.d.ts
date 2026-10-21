export type DeckSource = 'startup' | 'resume' | 'clear' | 'compact'
export type DeckStatus = { text: string; warn?: boolean }
export type DeckButton = { label: string; prompt: string }
export type DeckBaton = DeckButton & { summary?: string }
export type Deck = {
  v: 1
  source: DeckSource
  repo: string
  status: DeckStatus[]
  actions: DeckButton[]
  batons: DeckBaton[]
  handoff: string
  /** One SessionStart run's mark: the same deck through the context and the file applies once. */
  stamp?: string
}
export type DeckMode = 'menu' | 'handoff' | 'hidden'

declare module 'claude-code' {
  interface PluginState {
    cortexes: { deck: Deck | null; mode: DeckMode; reminded: boolean; percent: number }
  }
}
