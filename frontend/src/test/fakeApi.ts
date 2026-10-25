import { vi } from 'vitest'
import type { Song } from '../api'
import { makePage } from './fixtures'

export interface Call {
  method: string
  url: URL
  body?: unknown
  signal?: AbortSignal | null
}

type Handler = (call: Call) => Response | Promise<Response> | undefined

const key = (text: string) => text.trim().split(/\s+/).join(' ').toLowerCase()

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

/**
 * A stand-in for the backend: GET /songs filters (title substring, normalized), sorts (nulls last,
 * ties by id) and paginates; PUT /songs/{id}/rating stores a rating. `calls` records every request.
 * A test can intercept requests with `override` (return undefined to fall through to the default).
 */
export function installFakeApi(initial: Song[]) {
  const songs = initial.map((s) => ({ ...s }))
  const calls: Call[] = []
  let override: Handler = () => undefined

  const listSongs = (url: URL) => {
    const p = url.searchParams
    const page = Number(p.get('page') ?? 1)
    const size = Number(p.get('size') ?? 10)
    const title = p.get('title')
    let rows = title && key(title) ? songs.filter((s) => s.title !== null && key(s.title).includes(key(title))) : [...songs]
    const field = p.get('sort_by') as keyof Song | null
    if (field) {
      const dir = p.get('order') === 'desc' ? -1 : 1
      const cmp = (a: Song, b: Song) => {
        const x = a[field]
        const y = b[field]
        if (x === null || y === null) return x === y ? a.id.localeCompare(b.id) : x === null ? 1 : -1
        return x < y ? -dir : x > y ? dir : a.id.localeCompare(b.id)
      }
      rows = rows.sort(cmp)
    }
    const total = rows.length
    return json({ ...makePage(rows.slice((page - 1) * size, page * size), page, total, size) })
  }

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const call: Call = {
      method: init?.method ?? 'GET',
      url,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      signal: init?.signal,
    }
    calls.push(call)
    const overridden = override(call)
    if (overridden) return overridden
    if (call.method === 'GET' && url.pathname === '/songs') return listSongs(url)
    const match = url.pathname.match(/^\/songs\/([^/]+)\/rating$/)
    if (call.method === 'PUT' && match) {
      const id = decodeURIComponent(match[1])
      const song = songs.find((s) => s.id === id)
      if (!song) return json({ detail: `Song not found: ${id}` }, 404)
      song.rating = (call.body as { rating: number }).rating
      return json({ song_id: id, rating: song.rating })
    }
    return json({ detail: 'Not Found' }, 404)
  })

  return {
    songs,
    calls,
    fetchMock,
    /** Only the GET /songs requests, as plain objects of query parameters. */
    listCalls: () => calls.filter((c) => c.method === 'GET').map((c) => Object.fromEntries(c.url.searchParams)),
    putCalls: () => calls.filter((c) => c.method === 'PUT'),
    intercept: (handler: Handler) => {
      override = handler
    },
  }
}

/** A promise you resolve by hand, for holding a request open. */
export function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

/** A held response that rejects with an AbortError if the request is aborted, like real fetch. */
export function heldResponse(signal: AbortSignal | null | undefined) {
  const gate = deferred<Response>()
  const promise = new Promise<Response>((resolve, reject) => {
    gate.promise.then(resolve)
    signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
  })
  return { promise, respond: gate.resolve }
}

export { json }
