import type { Song } from './api'
import { COLUMNS } from './columns'

export const CSV_FILENAME = 'songs.csv'

/** RFC 4180: quote a field that holds a comma, quote, CR or LF, and double any quotes inside it. */
export function escapeCsvField(value: string | number | null | undefined): string {
  if (value == null) return '' // every missing value is an empty field
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/**
 * CSV for the given songs, in the order given. Columns are the displayed ones, headed by the
 * API field names; values are the raw API values (duration in ms, not rounded to m:ss).
 */
export function toCsv(songs: Song[]): string {
  const header = COLUMNS.map((column) => column.field)
  const rows = songs.map((song) => COLUMNS.map((column) => escapeCsvField(song[column.field])))
  return [header, ...rows].map((row) => row.join(',')).join('\r\n') + '\r\n'
}

/** Saves `csv` as songs.csv. A leading BOM makes Excel read the file as UTF-8. */
export function downloadCsv(csv: string): void {
  const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = CSV_FILENAME
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
