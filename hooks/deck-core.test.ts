import { describe, expect, test } from 'claude-code/testing'
import {
  cutMenu, deckPath, HANDOFF_THRESHOLD, MENU_END, MENU_START,
  modeAfterSubmit, modeForDeck, parseDeck, reminderStep,
} from './deck-core.ts'

const DECK = {
  v: 1, source: 'startup', repo: 'cortex',
  status: [{ text: '有 2 個 commit 尚未推送', warn: true }],
  actions: [{ label: '載入記憶', prompt: 'p1' }],
  batons: [{ label: 'line', prompt: 'p5' }],
  handoff: 'h',
}
const deckLine = (deck: unknown) =>
  `<!-- cortex:deck ${JSON.stringify(deck).replace(/</g, '\\u003c').replace(/>/g, '\\u003e')} -->`
const block = (line = deckLine(DECK)) =>
  `${MENU_START}\n${line}\n在你第一次回覆使用者時，呈現以下格式：\n1. ...\n${MENU_END}\n`

describe('cutMenu', () => {
  test('cuts only the fenced block and returns its deck', () => {
    const cut = cutMenu(`before\n[Cortexes] front\n\n${block()}after`)
    expect(cut?.text).toBe('before\n[Cortexes] front\n\nafter')
    expect(cut?.deck.repo).toBe('cortex')
  })
  test('runs to the last closing sentinel', () => {
    const quoted = `${MENU_START}\n${deckLine(DECK)}\n5. 載入交接［x］：quotes ${MENU_END} here\n${MENU_END}\nafter`
    expect(cutMenu(quoted)?.text).toBe('after')
  })
  test('no opening sentinel', () => expect(cutMenu('plain text')).toBeNull())
  test('no closing sentinel', () => expect(cutMenu(block().replace(MENU_END, ''))).toBeNull())
  test('no deck line', () => expect(cutMenu(`${MENU_START}\n在你第一次回覆\n${MENU_END}`)).toBeNull())
  test('broken JSON', () => expect(cutMenu(block('<!-- cortex:deck {broken -->'))).toBeNull())
  test('escaped angle brackets read back', () => {
    const deck = { ...DECK, batons: [{ label: 'a-->b<c', prompt: 'p' }] }
    expect(cutMenu(block(deckLine(deck)))?.deck.batons[0].label).toBe('a-->b<c')
  })
})

describe('deckPath', () => {
  test('one file per session under the plugin root', () =>
    expect(deckPath('/plug', 'abc-123')).toBe('/plug/.deck/abc-123.json'))
  test('an id that could leave the folder has no file', () => expect(deckPath('/plug', '../x')).toBeNull())
})

describe('parseDeck', () => {
  test('a version-1 deck', () => expect(parseDeck(JSON.stringify(DECK))?.handoff).toBe('h'))
  test('keeps the stamp', () => expect(parseDeck(JSON.stringify({ ...DECK, stamp: 's1' }))?.stamp).toBe('s1'))
  test('a deck without a stamp has none', () => expect(parseDeck(JSON.stringify(DECK))?.stamp).toBeUndefined())
  test('a stamp that is not a string', () =>
    expect(parseDeck(JSON.stringify({ ...DECK, stamp: 1 }))).toBeNull())
  test('another version', () => expect(parseDeck(JSON.stringify({ ...DECK, v: 2 }))).toBeNull())
  test('a malformed button', () =>
    expect(parseDeck(JSON.stringify({ ...DECK, actions: [{ label: 1, prompt: 'p' }] }))).toBeNull())
  test('a malformed status', () =>
    expect(parseDeck(JSON.stringify({ ...DECK, status: [{ text: 't', warn: 'yes' }] }))).toBeNull())
  test('a baton keeps its summary', () => {
    const batons = [{ label: 'line', summary: 'what it was', prompt: 'p5' }]
    expect(parseDeck(JSON.stringify({ ...DECK, batons }))?.batons[0].summary).toBe('what it was')
  })
  test('a malformed baton summary', () =>
    expect(parseDeck(JSON.stringify({ ...DECK, batons: [{ label: 'l', summary: 3, prompt: 'p' }] }))).toBeNull())
  test('not an object', () => expect(parseDeck('"text"')).toBeNull())
  test('an unknown source starts', () =>
    expect(parseDeck(JSON.stringify({ ...DECK, source: 'weird' }))?.source).toBe('startup'))
  test('a missing source starts', () => {
    const { source: _, ...rest } = DECK
    expect(parseDeck(JSON.stringify(rest))?.source).toBe('startup')
  })
})

describe('modes', () => {
  test('a compaction keeps the band down', () =>
    expect(modeForDeck({ ...DECK, source: 'compact' } as never)).toBe('hidden'))
  test('any other start shows the menu', () => {
    for (const source of ['startup', 'resume', 'clear']) {
      expect(modeForDeck({ ...DECK, source } as never)).toBe('menu')
    }
  })
  test('a submitted prompt folds the menu only', () => {
    expect(modeAfterSubmit('menu')).toBe('hidden')
    expect(modeAfterSubmit('handoff')).toBe('handoff')
    expect(modeAfterSubmit('hidden')).toBe('hidden')
  })
})

describe('reminderStep', () => {
  test('fires once per window, re-arms below the threshold', () => {
    let reminded = false
    const fires: boolean[] = []
    for (const pct of [69, 70, 75, 30, 72]) {
      const step = reminderStep(pct, reminded)
      reminded = step.reminded
      fires.push(step.fire)
    }
    expect(fires).toEqual([false, true, false, false, true])
    expect(HANDOFF_THRESHOLD).toBe(70)
  })
  test('a reading without a percentage changes nothing', () => {
    expect(reminderStep(undefined, true)).toEqual({ reminded: true, fire: false })
    expect(reminderStep(undefined, false)).toEqual({ reminded: false, fire: false })
  })
})
