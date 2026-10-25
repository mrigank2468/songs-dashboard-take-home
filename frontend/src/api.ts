// Types and calls for the backend in ../backend (see the README for the contract).

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

export const PAGE_SIZE = 10

/** Mirrors the backend's public `Song`. The internal `sources` field is never sent. */
export interface Song {
  id: string
  title: string | null
  danceability: number | null
  energy: number | null
  mood: number | null
  acousticness: number | null
  tempo: number | null
  duration_ms: number | null
  num_sections: number | null
  num_segments: number | null
  valence: number | null
  rating: number | null
}

export interface SongPage {
  songs: Song[]
  page: number
  size: number
  total: number
  total_pages: number
}

export interface RatingResponse {
  song_id: string
  rating: number | null
}

/** The backend accepts every Song field; the table sorts by the displayed ones. */
export type SortField = 'title' | 'tempo' | 'danceability' | 'energy' | 'mood' | 'duration_ms' | 'valence' | 'rating'
export type SortOrder = 'asc' | 'desc'

export interface SongsQuery {
  page: number // 1-based, as the backend expects
  sortBy: SortField | null
  order: SortOrder
  title: string // blank means no filter
}

export function buildSongsUrl(query: SongsQuery, baseUrl: string = API_BASE_URL): string {
  const url = new URL('/songs', baseUrl)
  url.searchParams.set('page', String(query.page))
  url.searchParams.set('size', String(PAGE_SIZE))
  if (query.sortBy) {
    url.searchParams.set('sort_by', query.sortBy)
    url.searchParams.set('order', query.order)
  }
  const title = query.title.trim()
  if (title) url.searchParams.set('title', title) // the backend normalizes case and inner whitespace
  return url.toString()
}

/** Turns an error response into a readable message (backend errors use a `detail` field). */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`.replace(/^: /, ''))
        .join('; ')
    }
  } catch {
    // not JSON; fall through
  }
  return `Request failed (HTTP ${response.status})`
}

async function request(url: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error(`Could not reach the API at ${API_BASE_URL}. Is the backend running?`)
  }
  if (!response.ok) throw new Error(await errorMessage(response))
  return response
}

export async function fetchSongs(query: SongsQuery, signal?: AbortSignal): Promise<SongPage> {
  const response = await request(buildSongsUrl(query), { signal })
  return response.json()
}

export async function putRating(songId: string, rating: number): Promise<RatingResponse> {
  const url = new URL(`/songs/${encodeURIComponent(songId)}/rating`, API_BASE_URL)
  const response = await request(url.toString(), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating }),
  })
  return response.json()
}
