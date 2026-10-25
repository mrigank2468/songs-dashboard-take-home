import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildSongsUrl, fetchSongs, putRating } from './api'
import type { SongsQuery } from './api'
import { makePage, makeSong } from './test/fixtures'

const BASE = 'http://api.test'
const query = (overrides: Partial<SongsQuery> = {}): SongsQuery => ({ page: 1, sortBy: null, order: 'asc', title: '', ...overrides })
const params = (q: SongsQuery) => Object.fromEntries(new URL(buildSongsUrl(q, BASE)).searchParams)

afterEach(() => vi.unstubAllGlobals())

describe('buildSongsUrl', () => {
  it('sends page and a fixed size of 10 by default, with no sort or title', () => {
    expect(params(query())).toEqual({ page: '1', size: '10' })
    expect(buildSongsUrl(query(), BASE)).toMatch(/^http:\/\/api\.test\/songs\?/)
  })

  it('sends sort_by and order together, only when a sort is chosen', () => {
    expect(params(query({ sortBy: 'duration_ms', order: 'desc', page: 3 }))).toEqual({
      page: '3',
      size: '10',
      sort_by: 'duration_ms',
      order: 'desc',
    })
    expect(params(query({ order: 'desc' }))).not.toHaveProperty('order') // order alone means nothing to the API
  })

  it('trims the title and omits it when blank', () => {
    expect(params(query({ title: '  Never Gonna  ' })).title).toBe('Never Gonna')
    expect(params(query({ title: '   ' }))).not.toHaveProperty('title')
    expect(params(query({ title: '' }))).not.toHaveProperty('title')
  })

  it('leaves inner whitespace and case to the backend and encodes special characters', () => {
    const url = buildSongsUrl(query({ title: 'a  B&c=d é' }), BASE)
    expect(new URL(url).searchParams.get('title')).toBe('a  B&c=d é')
    expect(url).not.toContain('&c=d')
  })
})

describe('fetchSongs', () => {
  it('requests the built URL with the abort signal and returns the page', async () => {
    const page = makePage([makeSong(1)])
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(page)))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    expect(await fetchSongs(query({ page: 2 }), controller.signal)).toEqual(page)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/songs?page=2&size=10')
    expect(init.signal).toBe(controller.signal)
  })

  it('turns a 422 validation error into a readable message', async () => {
    const detail = [{ loc: ['query', 'size'], msg: 'Input should be less than or equal to 100' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })))
    await expect(fetchSongs(query())).rejects.toThrow('size: Input should be less than or equal to 100')
  })

  it('uses a string detail as is, and falls back to the HTTP status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Song not found: x' }), { status: 404 })))
    await expect(fetchSongs(query())).rejects.toThrow('Song not found: x')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>oops</html>', { status: 500 })))
    await expect(fetchSongs(query())).rejects.toThrow('Request failed (HTTP 500)')
  })

  it('reports an unreachable API clearly, but lets an abort through unchanged', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(fetchSongs(query())).rejects.toThrow(/Could not reach the API.*backend running/)
    const abort = new DOMException('aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))
    await expect(fetchSongs(query())).rejects.toBe(abort)
  })
})

describe('putRating', () => {
  it('PUTs {"rating": n} as JSON to the song id route and returns the saved rating', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ song_id: 'abc', rating: 4 })))
    vi.stubGlobal('fetch', fetchMock)
    expect(await putRating('abc', 4)).toEqual({ song_id: 'abc', rating: 4 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/songs\/abc\/rating$/)
    expect(init.method).toBe('PUT')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ rating: 4 })
  })

  it('encodes the song id in the path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ song_id: 'a/b', rating: 1 })))
    vi.stubGlobal('fetch', fetchMock)
    await putRating('a/b c', 1)
    expect(fetchMock.mock.calls[0][0]).toContain('/songs/a%2Fb%20c/rating')
  })

  it('rejects with the backend message on 404 and 422', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Song not found: nope' }), { status: 404 })))
    await expect(putRating('nope', 3)).rejects.toThrow('Song not found: nope')
    const detail = [{ loc: ['body', 'rating'], msg: 'Input should be less than or equal to 5' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })))
    await expect(putRating('x', 6)).rejects.toThrow('rating: Input should be less than or equal to 5')
  })
})
