import { expect, it } from 'vitest'
import { createAppearanceMotionPolicy } from './appearanceMotionPolicy'

it('keeps the reveal for normal or unavailable hardware hints', () => {
  const policy = createAppearanceMotionPolicy()
  expect(policy.choose({ cores: 8, memory: 8 }, 0)).toBe('reveal')
  expect(policy.choose({}, 0)).toBe('reveal')
  expect(policy.choose({ cores: 0, memory: 0 }, 0)).toBe('reveal')
})

it.each([{ cores: 2 }, { memory: 2 }])('starts with a short fade on limited hardware: %j', (hardware) => {
  expect(createAppearanceMotionPolicy().choose(hardware, 0)).toBe('fade')
})

it.each([[119, 'reveal'], [120, 'fade'], [400, 'none']] as const)('degrades after a %i ms capture to %s', (duration, expected) => {
  const policy = createAppearanceMotionPolicy()
  policy.capture(duration, 1000)
  expect(policy.choose({}, 1000)).toBe(expected)
})

it('retries the reveal after the one minute cooldown', () => {
  const policy = createAppearanceMotionPolicy()
  policy.capture(150, 1000)
  expect(policy.choose({}, 60_999)).toBe('fade')
  expect(policy.choose({}, 61_000)).toBe('reveal')
})

it('ignores one isolated slow frame and tolerates regular 30 Hz frames', () => {
  const policy = createAppearanceMotionPolicy()
  expect(policy.frame(80, 80)).toBe(false)
  expect(policy.frame(33.4, 114)).toBe(false)
  expect(policy.frame(33.4, 147)).toBe(false)
  expect(policy.choose({}, 147)).toBe('reveal')
})

it.each([[45, 'fade'], [110, 'none']] as const)('stops after consecutive %i ms frames and selects %s next time', (interval, expected) => {
  const policy = createAppearanceMotionPolicy()
  expect(policy.frame(interval, interval)).toBe(false)
  expect(policy.frame(interval, interval * 2)).toBe(true)
  expect(policy.choose({}, interval * 2)).toBe(expected)
})

it('resets frame sampling for each animation', () => {
  const policy = createAppearanceMotionPolicy()
  policy.frame(45, 45)
  policy.begin()
  expect(policy.frame(45, 90)).toBe(false)
})
