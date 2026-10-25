import { describe, expect, it } from 'vitest'
import { formatDuration, formatNumber, NO_VALUE } from './format'

describe('formatDuration', () => {
  it.each([
    [225_947, '3:46'],
    [60_000, '1:00'],
    [59_499, '0:59'],
    [59_500, '1:00'],
    [158_000, '2:38'],
    [0, '0:00'],
    [3_600_000, '60:00'],
  ])('%i ms -> %s', (ms, expected) => expect(formatDuration(ms)).toBe(expected))

  it('shows a dash for a missing duration', () => {
    expect(formatDuration(null)).toBe(NO_VALUE)
    expect(formatDuration(undefined)).toBe(NO_VALUE)
  })
})

describe('formatNumber', () => {
  it('shows up to 3 decimals, keeps zero, and uses a dash for null', () => {
    expect(formatNumber(125.972)).toBe('125.972')
    expect(formatNumber(0.00531)).toBe('0.005')
    expect(formatNumber(0.5)).toBe('0.5')
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(1)).toBe('1')
    expect(formatNumber(null)).toBe(NO_VALUE)
  })
})
