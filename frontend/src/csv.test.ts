import { afterEach, describe, expect, it, vi } from 'vitest'
import { CSV_FILENAME, downloadCsv, escapeCsvField, toCsv } from './csv'
import { makeSong } from './test/fixtures'

describe('escapeCsvField', () => {
  it.each([
    ['plain', 'plain'],
    ['a,b', '"a,b"'],
    ['say "hi"', '"say ""hi"""'],
    ['line1\nline2', '"line1\nline2"'],
    ['line1\r\nline2', '"line1\r\nline2"'],
    ['cr\rhere', '"cr\rhere"'],
    ['"', '""""'],
    ['a, "b"\nc', '"a, ""b""\nc"'],
    ['', ''],
    [' padded ', ' padded '],
    ['Café', 'Café'],
  ])('%j -> %j', (input, expected) => {
    expect(escapeCsvField(input)).toBe(expected)
  })

  it('writes null and undefined as an empty field and numbers as plain text', () => {
    expect(escapeCsvField(null)).toBe('')
    expect(escapeCsvField(undefined)).toBe('')
    expect(escapeCsvField(0)).toBe('0') // zero is a value, not a missing one
    expect(escapeCsvField(0.00531)).toBe('0.00531')
    expect(escapeCsvField(-1.5)).toBe('-1.5')
  })
})

describe('toCsv', () => {
  it('has a header of the displayed columns and no id column', () => {
    const [header] = toCsv([makeSong(1)]).split('\r\n')
    expect(header).toBe('title,tempo,danceability,energy,mood,duration_ms,valence,rating')
    expect(toCsv([makeSong(1)])).not.toContain('id001')
  })

  it('keeps the given row order and writes raw values', () => {
    const csv = toCsv([makeSong(3, { title: 'C', rating: 5 }), makeSong(1, { title: 'A', tempo: 125.972 })])
    expect(csv.split('\r\n')).toEqual([
      'title,tempo,danceability,energy,mood,duration_ms,valence,rating',
      'C,120,0.5,0.7,1,203000,0.4,5',
      'A,125.972,0.5,0.7,1,201000,0.4,',
      '',
    ])
  })

  it('writes every null the same way (empty) but keeps 0', () => {
    const song = makeSong(0, { title: null, tempo: null, energy: null, valence: null, duration_ms: null, rating: null, mood: 0 })
    expect(toCsv([song]).split('\r\n')[1]).toBe(',,0.5,,0,,,')
  })

  it('escapes titles with commas, quotes and newlines inside a row', () => {
    const csv = toCsv([makeSong(1, { title: 'Hello, "World"\nPart 2' })])
    expect(csv.split('\r\n').slice(1).join('\r\n')).toBe('"Hello, ""World""\nPart 2",120,0.5,0.7,1,201000,0.4,\r\n')
  })

  it('is just the header for an empty list', () => {
    expect(toCsv([])).toBe('title,tempo,danceability,energy,mood,duration_ms,valence,rating\r\n')
  })
})

describe('downloadCsv', () => {
  afterEach(() => vi.restoreAllMocks())

  it('saves a file named songs.csv containing the CSV with a UTF-8 BOM', async () => {
    let blob: Blob | undefined
    URL.createObjectURL = vi.fn((b: Blob) => ((blob = b), 'blob:fake'))
    URL.revokeObjectURL = vi.fn()
    let name = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      name = this.download
    })
    downloadCsv('a,b\r\n')
    expect(CSV_FILENAME).toBe('songs.csv')
    expect(name).toBe('songs.csv')
    expect(blob?.type).toContain('text/csv')
    // Read the raw bytes: Blob.text() would silently drop the BOM while decoding.
    const bytes = new Uint8Array((await blob?.arrayBuffer()) ?? new ArrayBuffer(0))
    expect(Array.from(bytes.slice(0, 3))).toEqual([0xef, 0xbb, 0xbf])
    expect(new TextDecoder('utf-8', { ignoreBOM: true }).decode(bytes)).toBe('﻿a,b\r\n')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake')
  })
})
