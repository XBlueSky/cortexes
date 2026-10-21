import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

const PROPS = { hasSurvey: false, isWorking: false, maxRows: 20 } as never
const NO_BAND = 'no implementation for ui.render'

const deckOf = (source: string, batons: object[] = [{ label: 'line-a', prompt: 'resume line-a' }]) => ({
  v: 1, source, repo: 'cortex',
  status: [{ text: '有 2 個 commit 尚未推送', warn: true }],
  actions: [
    { label: '載入記憶', prompt: 'load memory' },
    { label: '最近紀錄', prompt: 'recent raws' },
    { label: '處理待辦', prompt: 'process backlog' },
  ],
  batons,
  handoff: 'write a baton',
})

const hookText = (deck: unknown) =>
  '[Cortexes] front\n\n<!-- cortex:menu -->\n' +
  `<!-- cortex:deck ${JSON.stringify(deck)} -->\n` +
  '在你第一次回覆使用者時，呈現以下格式：\n<!-- /cortex:menu -->\nOTHER PLUGIN'

/** Records each row's text as it reaches the engine, after the plugin's rewrite. */
function recordRows(on: On): string[] {
  const rows: string[] = []
  on('session.append', ($, e, next) => {
    rows.push(e.message.content.map(b => (b.type === 'text' ? b.text : `[${b.type}]`)).join('|'))
    return next(e)
  })
  return rows
}

let rowId = 0
/** Appends one row; nothing beneath the test stores rows, so the engine's refusal is expected. */
async function append($: Engine, texts: string[], door: 'hook-context' | 'prompt' = 'hook-context') {
  const content = texts.map(text => ({ type: 'text', text }))
  const message = door === 'prompt'
    ? { type: 'user', role: 'user', content }
    : { type: 'attachment', name: 'hook_additional_context', content }
  const origin = door === 'prompt' ? { kind: 'person' } : { kind: 'hook' }
  try {
    await $.session.append({ door, origin, uuid: `row-${++rowId}`, message } as never)
  } catch {
    // "no implementation for session.append": the test stands for the engine
  }
}

/** Records submitted prompts and answers them as the engine would. */
function recordSubmits(on: On): { text: string; asUser?: boolean }[] {
  const subs: { text: string; asUser?: boolean }[] = []
  on('prompt.submit', ($, e) => {
    subs.push({ text: e.text, asUser: (e.origin as { asUser?: boolean } | undefined)?.asUser })
    return { text: e.text }
  })
  return subs
}

function recordToasts(on: On): string[] {
  const toasts: string[] = []
  on('ui.toast', ($, e) => {
    toasts.push((e as { text: string }).text)
    return { value: undefined } as never
  })
  return toasts
}

function answerMeasure(on: On): void {
  on('session.measure', ($, e) => ({ changed: e.changed }))
}

const measure = ($: Engine, pct: number) =>
  $.session.measure({ context: { window: 200000, tokens: pct * 2000, percent: pct }, rateLimits: [], changed: [] } as never)

const mountBand = ($: Engine, surface: 'terminal' | 'desktop' = 'terminal') =>
  $.ui.mount({ plugin: 'cortexes', surface, component: 'AbovePrompt', props: PROPS })

describe('menu block', () => {
  test('a hook-context row loses only the fenced block', async ($, on) => {
    const rows = recordRows(on)
    await append($, [hookText(deckOf('startup'))])
    expect(rows).toEqual(['[Cortexes] front\n\nOTHER PLUGIN'])
  })

  test('the block is found in a later text block too', async ($, on) => {
    const rows = recordRows(on)
    await append($, ['OTHER PLUGIN FIRST', hookText(deckOf('startup'))])
    expect(rows).toEqual(['OTHER PLUGIN FIRST|[Cortexes] front\n\nOTHER PLUGIN'])
  })

  test('rows from other doors keep the block', async ($, on) => {
    const rows = recordRows(on)
    const text = hookText(deckOf('startup'))
    await append($, [text], 'prompt')
    expect(rows).toEqual([text])
  })

  test('a row whose deck is not a deck stays whole and draws no band', async ($, on) => {
    const rows = recordRows(on)
    const text = hookText({ ...deckOf('startup'), v: 2 })
    await append($, [text])
    expect(rows).toEqual([text])
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })
})

describe('band', () => {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`draws the deck and sends a button's prompt as the user (${surface})`, async ($, on) => {
      recordRows(on)
      const subs = recordSubmits(on)
      await append($, [hookText(deckOf('startup'))])
      const ui = await mountBand($, surface)
      expect((await ui.find({ type: 'Text', text: 'cortexes' }))?.props.color).toBe('claude')
      expect((await ui.find({ type: 'Text', text: '· 有 2 個 commit 尚未推送' }))?.props.color).toBe('warning')
      expect(await ui.find({ type: 'Button', text: '接續交接 line-a' })).toBeDefined()
      await ui.press({ key: 'action-0' })
      expect(subs).toEqual([{ text: 'load memory', asUser: true }])
      await expect(mountBand($, surface)).rejects.toThrow(NO_BAND)
    })
  }

  test('the menu is a framed card of numbered buttons', async ($, on) => {
    recordRows(on)
    await append($, [hookText(deckOf('startup'))])
    const ui = await mountBand($)
    expect(await ui.drawn()).toMatchObject({ props: { borderStyle: 'round', borderColor: 'subtle' } })
    const hotkeys = await Promise.all(['action-0', 'action-1', 'action-2', 'baton-0']
      .map(async key => (await ui.find({ key }))?.props))
    expect(hotkeys.map(p => [p?.plain, p?.hotkey])).toEqual([[true, '1'], [true, '2'], [true, '3'], [true, '4']])
    expect((await ui.find({ key: 'hide' }))?.props).toMatchObject({ plain: true, dimColor: true })
    expect((await ui.find({ key: 'hide' }))?.props.hotkey).toBeUndefined()
  })

  test('a baton shows its summary dim beside the button', async ($, on) => {
    recordRows(on)
    const batons = [{ label: 'line-a', summary: 'what line-a was doing', prompt: 'resume line-a' }]
    await append($, [hookText(deckOf('startup', batons))])
    const summary = await (await mountBand($)).find({ type: 'Text', text: 'what line-a was doing' })
    expect(summary?.props).toMatchObject({ dimColor: true, wrap: 'truncate-end' })
  })

  test('a baton button sends its resume prompt', async ($, on) => {
    recordRows(on)
    const subs = recordSubmits(on)
    await append($, [hookText(deckOf('startup'))])
    await (await mountBand($)).press({ key: 'baton-0' })
    expect(subs).toEqual([{ text: 'resume line-a', asUser: true }])
  })

  test('any submitted prompt folds the menu', async ($, on) => {
    recordRows(on)
    recordSubmits(on)
    await append($, [hookText(deckOf('startup'))])
    await $.prompt.submit({ text: 'typed by the person' })
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })

  test('a survey holds the band', async ($, on) => {
    recordRows(on)
    await append($, [hookText(deckOf('startup'))])
    const props = { hasSurvey: true, isWorking: false, maxRows: 20 } as never
    await expect($.ui.mount({ plugin: 'cortexes', surface: 'terminal', component: 'AbovePrompt', props }))
      .rejects.toThrow(NO_BAND)
  })

  test('the hide button folds the menu', async ($, on) => {
    recordRows(on)
    await append($, [hookText(deckOf('startup'))])
    await (await mountBand($)).press({ key: 'hide' })
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })

  test('after a compaction the block is cut but no band shows', async ($, on) => {
    const rows = recordRows(on)
    await append($, [hookText(deckOf('compact'))])
    expect(rows).toEqual(['[Cortexes] front\n\nOTHER PLUGIN'])
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })

  test('many batons all stay pressable', async ($, on) => {
    recordRows(on)
    const subs = recordSubmits(on)
    const batons = Array.from({ length: 12 }, (_, i) => ({ label: `line-${i}`, prompt: `resume line-${i}` }))
    await append($, [hookText(deckOf('startup', batons))])
    const ui = await mountBand($)
    expect(await ui.find({ type: 'Button', text: '接續交接 line-11' })).toBeDefined()
    expect((await ui.find({ key: 'baton-5' }))?.props.hotkey).toBe('9')
    expect((await ui.find({ key: 'baton-6' }))?.props.hotkey).toBeUndefined()
    await ui.press({ key: 'baton-11' })
    expect(subs).toEqual([{ text: 'resume line-11', asUser: true }])
  })

  test('a new session start replaces a hand-off band with the menu', async ($, on) => {
    recordRows(on)
    recordToasts(on)
    answerMeasure(on)
    await append($, [hookText(deckOf('startup'))])
    await measure($, 80)
    expect(await (await mountBand($)).find({ type: 'Button', text: '建立交接' })).toBeDefined()
    await append($, [hookText(deckOf('clear'))])
    expect(await (await mountBand($)).find({ type: 'Button', text: '載入記憶' })).toBeDefined()
  })
})

/**
 * Answers the session id and the deck files under the plugin root from
 * memory, as the host would; a missing file rejects the stat and the read.
 */
function deckFiles(on: On) {
  const files = new Map<string, { text: string; mtimeMs: number }>()
  const world = {
    id: 'sess-1',
    write(id: string, deck: unknown, mtimeMs: number, text = JSON.stringify(deck)) {
      files.set(id, { text, mtimeMs })
    },
  }
  const fileOf = (path: string) => {
    const f = files.get(/\/\.deck\/([^/]+)\.json$/.exec(path)?.[1] ?? '')
    if (f === undefined) throw new Error(`ENOENT: ${path}`)
    return f
  }
  on('session.id', () => ({ value: world.id }) as never)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('fs.stat', ($, e) => {
    const f = fileOf(e.path)
    return { value: { kind: 'file', size: f.text.length, mtimeMs: f.mtimeMs, isLink: false } } as never
  })
  on('fs.read', ($, e) => ({ value: fileOf(e.path).text }) as never)
  return world
}

const startSession = ($: Engine) => $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })

describe('deck file', () => {
  test('a deck file is drawn within a tick of appearing', async ($, on) => {
    const clock = mock.clock(on)
    const files = deckFiles(on)
    await startSession($)
    await clock.advance(1000)
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
    files.write('sess-1', { ...deckOf('startup'), stamp: 's1' }, 5)
    await clock.advance(1000)
    expect(await (await mountBand($)).find({ type: 'Button', text: '載入記憶' })).toBeDefined()
  })

  test('a /clear draws the new session\'s deck', async ($, on) => {
    const clock = mock.clock(on)
    const files = deckFiles(on)
    await startSession($)
    files.write('sess-1', { ...deckOf('startup'), stamp: 's1' }, 5)
    await clock.advance(1000)
    await (await mountBand($)).press({ key: 'hide' })
    files.id = 'sess-2'
    files.write('sess-2', { ...deckOf('clear', []), stamp: 's2' }, 9)
    await clock.advance(1000)
    const ui = await mountBand($)
    expect(await ui.find({ type: 'Button', text: '載入記憶' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: '接續交接 line-a' })).toBeUndefined()
  })

  test('a folded menu stays folded while its file is unchanged', async ($, on) => {
    const clock = mock.clock(on)
    const files = deckFiles(on)
    await startSession($)
    files.write('sess-1', { ...deckOf('startup'), stamp: 's1' }, 5)
    await clock.advance(1000)
    await (await mountBand($)).press({ key: 'hide' })
    await clock.advance(5000)
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })

  test('the deck the context already carried does not come back', async ($, on) => {
    recordRows(on)
    const clock = mock.clock(on)
    const files = deckFiles(on)
    await startSession($)
    const deck = { ...deckOf('startup'), stamp: 's1' }
    await append($, [hookText(deck)])
    await (await mountBand($)).press({ key: 'hide' })
    files.write('sess-1', deck, 5)
    await clock.advance(1000)
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })

  test('a file that is not a deck draws nothing', async ($, on) => {
    const clock = mock.clock(on)
    const files = deckFiles(on)
    await startSession($)
    files.write('sess-1', null, 5, '{broken')
    await clock.advance(1000)
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })
})

describe('context reminder', () => {
  test('fires once per window and offers a hand-off', async ($, on) => {
    recordRows(on)
    const subs = recordSubmits(on)
    const toasts = recordToasts(on)
    answerMeasure(on)
    await append($, [hookText(deckOf('startup'))])
    await $.prompt.submit({ text: 'work' })
    for (const pct of [69, 70, 75, 30, 72]) await measure($, pct)
    expect(toasts).toEqual(['context 已用 70%，可以考慮建立交接', 'context 已用 72%，可以考慮建立交接'])
    const ui = await mountBand($)
    expect(await ui.drawn()).toMatchObject({ props: { borderStyle: 'round', borderColor: 'subtle' } })
    expect(await ui.find({ type: 'Text', text: '· context 已用 72%' })).toBeDefined()
    // No digit: this band outlives prompts, and a prompt may start with one.
    expect((await ui.find({ key: 'handoff' }))?.props).toMatchObject({ variant: 'primary' })
    expect((await ui.find({ key: 'handoff' }))?.props.hotkey).toBeUndefined()
    await ui.press({ key: 'handoff' })
    expect(subs.at(-1)).toEqual({ text: 'write a baton', asUser: true })
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })

  test('a resumed session is reminded again', async ($, on) => {
    recordRows(on)
    const toasts = recordToasts(on)
    answerMeasure(on)
    await append($, [hookText(deckOf('startup'))])
    await measure($, 80)
    await measure($, 82)
    await append($, [hookText(deckOf('resume'))])
    await measure($, 83)
    expect(toasts).toEqual(['context 已用 80%，可以考慮建立交接', 'context 已用 83%，可以考慮建立交接'])
  })

  test('without a deck the reminder only toasts', async ($, on) => {
    const toasts = recordToasts(on)
    answerMeasure(on)
    await measure($, 75)
    expect(toasts).toEqual(['context 已用 75%，可以考慮建立交接'])
    await expect(mountBand($)).rejects.toThrow(NO_BAND)
  })
})
