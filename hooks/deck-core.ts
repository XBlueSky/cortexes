/**
 * @file Pure rules of the cortex deck: the fenced menu block that
 * session-start-inject.sh writes, the deck JSON on its first line, and the
 * band's state transitions. Nothing here touches `$`, so every rule is
 * tested without the engine (deck-core.test.ts).
 */
import type { Deck, DeckBaton, DeckButton, DeckMode, DeckSource, DeckStatus } from '../types'

/** Opening sentinel of the model-facing menu block. */
export const MENU_START = '<!-- cortex:menu -->'
/** Closing sentinel; the cut runs to the last one, so a quoted copy cannot end it early. */
export const MENU_END = '<!-- /cortex:menu -->'
const DECK_PREFIX = '<!-- cortex:deck '
const DECK_SUFFIX = ' -->'
/** Context use, in percent of the window, that raises the hand-off reminder. */
export const HANDOFF_THRESHOLD = 70

const SOURCES: readonly DeckSource[] = ['startup', 'resume', 'clear', 'compact']

const isRecord = (x: unknown): x is Record<string, unknown> =>
  typeof x === 'object' && x !== null && !Array.isArray(x)

const isButton = (x: unknown): x is DeckButton =>
  isRecord(x) && typeof x.label === 'string' && typeof x.prompt === 'string'

const isBaton = (x: unknown): x is DeckBaton =>
  isRecord(x) && isButton(x) && (x.summary === undefined || typeof x.summary === 'string')

const isStatus = (x: unknown): x is DeckStatus =>
  isRecord(x) && typeof x.text === 'string' && (x.warn === undefined || typeof x.warn === 'boolean')

/**
 * Parses a deck's JSON text.
 * @param json the text between the deck line's prefix and suffix
 * @returns the deck, or null when the text is not a version-1 deck
 */
export function parseDeck(json: string): Deck | null {
  let raw: unknown
  try {
    raw = JSON.parse(json)
  } catch {
    return null
  }
  if (!isRecord(raw) || raw.v !== 1) return null
  const { repo, handoff, status, actions, batons } = raw
  if (typeof repo !== 'string' || typeof handoff !== 'string') return null
  if (!Array.isArray(status) || !status.every(isStatus)) return null
  if (!Array.isArray(actions) || !actions.every(isButton)) return null
  if (!Array.isArray(batons) || !batons.every(isBaton)) return null
  const { stamp } = raw
  if (stamp !== undefined && typeof stamp !== 'string') return null
  const given = raw.source
  const source = SOURCES.find(s => s === given) ?? 'startup'
  return { v: 1, source, repo, handoff, status, actions, batons, ...(stamp === undefined ? {} : { stamp }) }
}

/**
 * Where session-start-inject.sh writes a session's deck: the file channel,
 * read where an organization's policy plugin keeps `session.append` from the
 * person's plugins and the context block never reaches the mod.
 * @param root the plugin's directory (`$.plugin.root`, the script's CLAUDE_PLUGIN_ROOT)
 * @param sessionId the session's id
 * @returns the file's path, or null for an id that is not a plain file name
 */
export function deckPath(root: string, sessionId: string): string | null {
  if (!/^[A-Za-z0-9_-]+$/.test(sessionId)) return null
  return `${root}/.deck/${sessionId}.json`
}

/** A text block with the menu cut out, and the deck the block carried. */
export type Cut = { text: string; deck: Deck }

/**
 * Cuts the fenced menu block out of one text block.
 *
 * The block runs from the first MENU_START to the last MENU_END and the
 * newline after it; the line right after MENU_START must be a version-1 deck.
 * @returns the cut, or null when anything is missing or malformed, so the
 *   caller passes the text on untouched and the model shows the text menu
 */
export function cutMenu(text: string): Cut | null {
  const start = text.indexOf(MENU_START)
  if (start < 0) return null
  const end = text.lastIndexOf(MENU_END)
  if (end < start) return null
  const lineStart = start + MENU_START.length + 1
  if (text[lineStart - 1] !== '\n') return null
  const lineEnd = text.indexOf('\n', lineStart)
  if (lineEnd < 0 || lineEnd > end) return null
  const line = text.slice(lineStart, lineEnd)
  if (!line.startsWith(DECK_PREFIX) || !line.endsWith(DECK_SUFFIX)) return null
  const deck = parseDeck(line.slice(DECK_PREFIX.length, line.length - DECK_SUFFIX.length))
  if (deck === null) return null
  let cutEnd = end + MENU_END.length
  if (text[cutEnd] === '\n') cutEnd += 1
  return { text: text.slice(0, start) + text.slice(cutEnd), deck }
}

/** The band's mode once a new deck arrives: down after a compaction, else the menu. */
export const modeForDeck = (deck: Deck): DeckMode => (deck.source === 'compact' ? 'hidden' : 'menu')

/** The band's mode after any prompt is submitted: the menu folds, a reminder stays. */
export const modeAfterSubmit = (mode: DeckMode): DeckMode => (mode === 'menu' ? 'hidden' : mode)

/** One measurement's effect on the reminder flag. */
export type ReminderStep = { reminded: boolean; fire: boolean }

/**
 * Applies one context measurement to the reminder flag: fire on the first
 * reading at or over the threshold, re-arm once a reading drops below it (a
 * compaction), and ignore a reading without a percentage (a fresh window).
 */
export function reminderStep(percent: number | undefined, reminded: boolean): ReminderStep {
  if (percent === undefined) return { reminded, fire: false }
  if (percent < HANDOFF_THRESHOLD) return { reminded: false, fire: false }
  return { reminded: true, fire: !reminded }
}
