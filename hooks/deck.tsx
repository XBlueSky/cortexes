/**
 * @file The cortexes deck: draws the SessionStart menu as a band above the
 * prompt, cuts the menu block from the model's context where the engine lets
 * it, and once per context window at 70% use offers a takeoff hand-off.
 *
 * session-start-inject.sh owns every fact and every prompt (the deck); this
 * module only draws and relays. Every failure passes the row on untouched, so
 * the model shows the text menu as it did before the mod.
 */
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Deck } from '../types'
import { cutMenu, deckPath, modeAfterSubmit, modeForDeck, parseDeck, reminderStep } from './deck-core.ts'

const deck = atom({ plugin: 'cortexes', key: 'deck' } as const, null)
const mode = atom({ plugin: 'cortexes', key: 'mode' } as const, 'hidden')
const reminded = atom({ plugin: 'cortexes', key: 'reminded' } as const, false)
const percent = atom({ plugin: 'cortexes', key: 'percent' } as const, 0)

/** How often the deck file is looked at, in milliseconds. */
const POLL_MS = 1000

/**
 * Takes one SessionStart run's deck, once: the context row and the deck file
 * may both carry it, and a menu the person folded must not come back.
 */
async function receive($: EngineInterface, d: Deck): Promise<void> {
  if (d.stamp !== undefined && (await read($, deck))?.stamp === d.stamp) return
  await update($, deck, () => d)
  await update($, mode, () => modeForDeck(d))
  if (d.source !== 'compact') await update($, reminded, () => false)
}

export const register: Register = on => {
  // Only the engine's hook-context row: a prompt or tool output that quotes
  // the sentinels (a cortex session about cortex) must reach the model whole.
  // Where an organization seats its policy plugin this hook never runs: the
  // block stays in the context and the deck file below draws the band.
  on('session.append', { door: 'hook-context' }, async ($, e, next) => {
    const content = [...e.message.content]
    let found: Deck | null = null
    for (const [i, block] of content.entries()) {
      if (block.type !== 'text') continue
      const cut = cutMenu(block.text)
      if (cut === null) continue
      content[i] = { ...block, text: cut.text }
      found = cut.deck
      break
    }
    if (found === null) return next(e)
    await receive($, found)
    return next({ ...e, message: { ...e.message, content } })
  }).catch(($, e, next) => next(e))

  // The deck file: session-start-inject.sh writes one per session id on every
  // SessionStart (startup, resume, /clear, compaction), which this process
  // sees no event for, so the file is watched for the whole session.
  on('session.start', async ($, e, next) => {
    let seen: number | null = null
    $.clock.every(POLL_MS, async () => {
      try {
        const path = deckPath($.plugin.root, await $.session.id())
        if (path === null) return
        const { mtimeMs } = await $.fs.stat(path)
        if (mtimeMs === seen) return
        seen = mtimeMs
        const d = parseDeck(await $.fs.read(path))
        if (d !== null) await receive($, d)
      } catch {
        // No file yet, or it went with SessionEnd: look again next tick.
      }
    })
    return next(e)
  }).catch(($, e, next) => next(e))

  on('prompt.submit', async ($, e, next) => {
    await update($, mode, modeAfterSubmit)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('session.measure', async ($, e, next) => {
    let fire = false
    await update($, reminded, was => {
      const step = reminderStep(e.context.percent, was)
      fire = step.fire
      return step.reminded
    })
    if (fire) {
      const pct = e.context.percent ?? 0
      await update($, percent, () => pct)
      $.ui.toast(`context 已用 ${pct}%，可以考慮建立交接`)
      if ((await read($, deck)) !== null) await update($, mode, () => 'handoff')
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const d = await read($, deck)
    const m = await read($, mode)
    if (e.props.hasSurvey || d === null || m === 'hidden') return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    // The band folds first: a hand-off band is not folded by prompt.submit.
    const send = (prompt: string) => async () => {
      await update($, mode, () => 'hidden')
      await $.prompt.submit({ text: prompt, asUser: true })
    }
    const hide = async () => {
      await update($, mode, () => 'hidden')
    }
    // The title row: the plugin's name, then the repo and the status, gray.
    const title = (repo: string | null, status: { text: string; warn?: boolean }[]) => (
      <Box key="title" columnGap={1} flexWrap="wrap">
        <Text bold color="claude">cortexes</Text>
        {repo === null ? [] : [<Box key="repo"><Text>{repo}</Text></Box>]}
        {status.map((s, i) => (
          <Box key={`status-${i}`}>
            <Text color={s.warn ? 'warning' : 'subtle'}>{`· ${s.text}`}</Text>
          </Box>
        ))}
      </Box>
    )
    const hideButton = <Button key="hide" plain dimColor label="收起" onPress={hide} />
    // Both bands draw as a gray rounded card, set off from the transcript above.
    if (m === 'handoff') {
      const pct = await read($, percent)
      // No digit hotkey: this band outlives prompts, and a bare digit typed
      // into the empty composer would press it instead of starting a prompt.
      return (
        <Box borderStyle="round" borderColor="subtle" paddingX={1} flexDirection="column">
          {title(null, [{ text: `context 已用 ${pct}%` }])}
          <Box columnGap={3}>
            <Button key="handoff" variant="primary" label="建立交接" onPress={send(d.handoff)} />
            {hideButton}
          </Box>
        </Box>
      )
    }
    // Digits 1-9 in deck order: a bare digit in the empty composer presses
    // the button, as the text menu's numbers were answered.
    const digit = (i: number) => (i < 9 ? String(i + 1) : undefined)
    return (
      <Box borderStyle="round" borderColor="subtle" paddingX={1} flexDirection="column">
        {title(d.repo, d.status)}
        <Box columnGap={3} flexWrap="wrap">
          {d.actions.map((a, i) => (
            <Button key={`action-${i}`} plain hotkey={digit(i)} label={a.label} onPress={send(a.prompt)} />
          ))}
          {hideButton}
        </Box>
        {d.batons.map((b, i) => (
          <Box key={`baton-row-${i}`} columnGap={2}>
            <Button
              key={`baton-${i}`}
              plain
              hotkey={digit(d.actions.length + i)}
              label={`接續交接 ${b.label}`}
              onPress={send(b.prompt)}
            />
            {b.summary ? [<Box key="summary" flexShrink={1}><Text dimColor wrap="truncate-end">{b.summary}</Text></Box>] : []}
          </Box>
        ))}
      </Box>
    )
  }).catch(($, e, next) => next(e))
}
