export const NO_VALUE = '—'

const numberFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 })

/** A number for display (up to 3 decimals), or a dash when there is no value. */
export function formatNumber(value: number | null | undefined): string {
  return value == null ? NO_VALUE : numberFormat.format(value)
}

/** Milliseconds as m:ss (rounded to the nearest second), or a dash when there is no value. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return NO_VALUE
  const totalSeconds = Math.round(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}
