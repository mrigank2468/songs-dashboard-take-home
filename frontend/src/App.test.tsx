import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App, { SEARCH_DEBOUNCE_MS } from './App'
import { downloadCsv } from './csv'
import { makePage, makeSong } from './test/fixtures'
import { heldResponse, installFakeApi, json } from './test/fakeApi'
import type { Song } from './api'

vi.mock('./csv', async (importOriginal) => ({ ...(await importOriginal<typeof import('./csv')>()), downloadCsv: vi.fn() }))

/** 25 songs: ids id000.., two titled "Perfect", one with several null values. */
function catalog(): Song[] {
  return Array.from({ length: 25 }, (_, n) => {
    const overrides: Partial<Song> = { tempo: 200 - n, energy: n % 2 ? 0.9 : 0.1 }
    if (n === 7 || n === 8) overrides.title = n === 7 ? 'Perfect' : 'perfect '
    if (n === 3) Object.assign(overrides, { title: null, tempo: null, valence: null, duration_ms: null, energy: null })
    return makeSong(n, overrides)
  })
}

let api: ReturnType<typeof installFakeApi>

beforeEach(() => {
  api = installFakeApi(catalog())
  vi.stubGlobal('fetch', api.fetchMock)
  vi.mocked(downloadCsv).mockClear()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const setup = () => userEvent.setup()
const bodyRows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)
const titlesOnPage = () => bodyRows().map((row) => within(row).getAllByRole('cell')[0].textContent)
const header = (name: RegExp) => screen.getByRole('columnheader', { name })

async function loaded() {
  await screen.findByRole('table')
  await waitFor(() => expect(screen.queryByRole('progressbar', { name: /loading songs/i })).not.toBeInTheDocument())
}

describe('loading and display', () => {
  it('fetches page 1 with 10 songs and no sort or title', async () => {
    render(<App />)
    await loaded()
    expect(api.listCalls()).toEqual([{ page: '1', size: '10' }])
    expect(screen.getByRole('heading', { name: /songs dashboard/i })).toBeInTheDocument()
    expect(bodyRows()).toHaveLength(10)
    expect(titlesOnPage().slice(0, 3)).toEqual(['Song 0', 'Song 1', 'Song 2'])
  })

  it('shows the requested columns, not the song id', async () => {
    render(<App />)
    await loaded()
    const names = within(screen.getByRole('table')).getAllByRole('columnheader').map((h) => h.textContent)
    expect(names).toEqual(['Title', 'Tempo (BPM)', 'Danceability', 'Energy', 'Mood', 'Duration', 'Valence', 'Rating'])
    expect(screen.queryByText('id000')).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /^id$/i })).not.toBeInTheDocument()
  })

  it('formats values and shows a dash for nulls', async () => {
    render(<App />)
    await loaded()
    const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((c) => c.textContent)
    expect(cells(bodyRows()[0]).slice(0, 7)).toEqual(['Song 0', '200', '0.5', '0.1', '0', '3:20', '0.4'])
    const nullRow = cells(bodyRows()[3]).slice(0, 7)
    expect(nullRow).toEqual(['—', '—', '0.5', '—', '1', '—', '—'])
  })

  it('shows correct pagination metadata and moves between pages', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    expect(screen.getByText('1–10 of 25 · page 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /previous page/i })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText('11–20 of 25 · page 2 of 3')).toBeInTheDocument())
    expect(api.listCalls().at(-1)).toEqual({ page: '2', size: '10' })
    expect(titlesOnPage()[0]).toBe('Song 10')

    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText('21–25 of 25 · page 3 of 3')).toBeInTheDocument())
    expect(bodyRows()).toHaveLength(5)
    expect(screen.getByRole('button', { name: /next page/i })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: /previous page/i }))
    await waitFor(() => expect(screen.getByText(/11–20 of 25/)).toBeInTheDocument())
  })

  it('shows a loading indicator until the first response arrives', async () => {
    const held = heldResponse(undefined)
    api.intercept(() => held.promise)
    render(<App />)
    expect(screen.getByRole('progressbar', { name: /loading songs/i })).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await act(async () => held.respond(json(makePage([makeSong(1)]))))
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar', { name: /loading songs/i })).not.toBeInTheDocument()
  })

  it('shows an error with a working Retry when the request fails', async () => {
    const user = setup()
    api.intercept(() => json({ detail: 'database exploded' }, 500))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('database exploded')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/of 25/)).not.toBeInTheDocument()

    api.intercept(() => undefined)
    await user.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('explains an unreachable backend', async () => {
    api.fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the api/i)
  })

  it('shows a message and "0 songs" when there are no results', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.type(screen.getByRole('searchbox'), 'no such song')
    expect(await screen.findByText(/no songs with the title “no such song”/i)).toBeInTheDocument()
    expect(screen.getByText('0 songs')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /export/i })).toBeDisabled()
  })

  it('shows an empty-dataset message when there is no search', async () => {
    api.intercept(() => json(makePage([], 1, 0)))
    render(<App />)
    expect(await screen.findByText('No songs found.')).toBeInTheDocument()
    expect(screen.getByText('0 songs')).toBeInTheDocument()
  })

  it('goes to the last real page if the requested page no longer exists', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    // The server answers "page 2 is empty, there is only 1 page", as if the data had shrunk.
    api.intercept((call) =>
      call.url.searchParams.get('page') === '2'
        ? json({ songs: [], page: 2, size: 10, total: 4, total_pages: 1 })
        : undefined,
    )
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(api.listCalls().map((c) => c.page)).toEqual(['1', '2', '1']))
    expect(await screen.findByText(/1–10 of 25 · page 1 of 3/)).toBeInTheDocument()
  })
})

describe('sorting', () => {
  it('starts ascending on the first click, toggles on repeats, and restarts ascending on a new column', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    expect(header(/tempo/i)).not.toHaveAttribute('aria-sort')

    await user.click(within(header(/tempo/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10', sort_by: 'tempo', order: 'asc' }))
    await waitFor(() => expect(header(/tempo/i)).toHaveAttribute('aria-sort', 'ascending'))

    await user.click(within(header(/tempo/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10', sort_by: 'tempo', order: 'desc' }))
    await waitFor(() => expect(header(/tempo/i)).toHaveAttribute('aria-sort', 'descending'))

    await user.click(within(header(/tempo/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toMatchObject({ sort_by: 'tempo', order: 'asc' }))

    await user.click(within(header(/energy/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10', sort_by: 'energy', order: 'asc' }))
    await waitFor(() => expect(header(/energy/i)).toHaveAttribute('aria-sort', 'ascending'))
    expect(header(/tempo/i)).not.toHaveAttribute('aria-sort')
  })

  it.each([
    ['Title', 'title'],
    ['Tempo', 'tempo'],
    ['Danceability', 'danceability'],
    ['Energy', 'energy'],
    ['Mood', 'mood'],
    ['Duration', 'duration_ms'],
    ['Valence', 'valence'],
    ['Rating', 'rating'],
  ])('the %s header sorts by %s on the server', async (label, field) => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.click(within(header(new RegExp(label, 'i'))).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toMatchObject({ sort_by: field, order: 'asc', page: '1' }))
  })

  it('sorts the whole dataset, not just the visible page', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    expect(titlesOnPage()).not.toContain('Song 24') // lowest tempo overall, but on the last page
    await user.click(within(header(/tempo/i)).getByRole('button'))
    await waitFor(() => expect(titlesOnPage()[0]).toBe('Song 24'))
    // nulls last: the song with a null tempo is on the last page, not first
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText(/21–25 of 25/)).toBeInTheDocument())
    expect(titlesOnPage().at(-1)).toBe('—')
  })

  it('goes back to page 1 when the sort changes', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText(/11–20/)).toBeInTheDocument())
    await user.click(within(header(/danceability/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toMatchObject({ page: '1', sort_by: 'danceability' }))
    expect(await screen.findByText(/1–10 of 25 · page 1 of 3/)).toBeInTheDocument()
    // and again when only the direction changes
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText(/11–20/)).toBeInTheDocument())
    await user.click(within(header(/danceability/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toMatchObject({ page: '1', order: 'desc' }))
  })

  it('keeps the sort when paging', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.click(within(header(/tempo/i)).getByRole('button'))
    await waitFor(() => expect(titlesOnPage()[0]).toBe('Song 24'))
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(api.listCalls().at(-1)).toEqual({ page: '2', size: '10', sort_by: 'tempo', order: 'asc' }))
  })
})

describe('title search', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
  const typing = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) })
  const searchbox = () => screen.getByRole('searchbox')

  it('waits 300 ms after the last keystroke and sends one request', async () => {
    const user = typing()
    render(<App />)
    await loaded()
    const before = api.listCalls().length
    await user.type(searchbox(), 'perf')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS - 100))
    expect(api.listCalls()).toHaveLength(before) // still typing: nothing sent
    await user.type(searchbox(), 'ect')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(api.listCalls()).toHaveLength(before + 1))
    expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10', title: 'perfect' })
  })

  it('shows every song with a matching title, whatever the case or spacing', async () => {
    const user = typing()
    render(<App />)
    await loaded()
    await user.type(searchbox(), '  PERFECT   ')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(bodyRows()).toHaveLength(2))
    expect(titlesOnPage()).toEqual(['Perfect', 'perfect '])
    expect(screen.getByText(/1–2 of 2 · page 1 of 1/)).toBeInTheDocument()
    expect(api.listCalls().at(-1)?.title).toBe('PERFECT') // trimmed; the server handles case
  })

  it('treats blank or whitespace-only input as no filter and does not refetch for it', async () => {
    const user = typing()
    render(<App />)
    await loaded()
    const before = api.listCalls().length
    await user.type(searchbox(), '   ')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    expect(api.listCalls()).toHaveLength(before) // same as no filter, so nothing new to fetch

    await user.type(searchbox(), 'perfect')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(bodyRows()).toHaveLength(2))
    await user.clear(searchbox())
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(bodyRows()).toHaveLength(10))
    expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10' }) // no title parameter at all
  })

  it('goes back to page 1 when the search changes, in one request', async () => {
    const user = typing()
    render(<App />)
    await loaded()
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText(/11–20/)).toBeInTheDocument())
    const before = api.listCalls().length
    await user.type(searchbox(), 'Song 5')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(api.listCalls()).toHaveLength(before + 1))
    expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10', title: 'Song 5' })
  })

  it('keeps the sort while searching', async () => {
    const user = typing()
    render(<App />)
    await loaded()
    await user.click(within(header(/tempo/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toMatchObject({ sort_by: 'tempo' }))
    await user.type(searchbox(), 'perfect')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10', title: 'perfect', sort_by: 'tempo', order: 'asc' }))
    expect(titlesOnPage()).toEqual(['perfect ', 'Perfect']) // tempo 192 then 193: filter, then sort
  })

  it('ignores a slow old response that arrives after a newer one', async () => {
    const user = typing()
    render(<App />)
    await loaded()
    const slow = heldResponse(undefined)
    const slowSignals: (AbortSignal | null | undefined)[] = []
    api.intercept((call) => {
      if (call.url.searchParams.get('title') === 'song 1') {
        slowSignals.push(call.signal)
        return heldResponse(call.signal).promise.then(() => slow.promise) // never resolves on its own
      }
      return undefined
    })
    // First search ("song 1") is slow; then the user changes the search to "perfect", which is fast.
    await user.type(searchbox(), 'song 1')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(slowSignals).toHaveLength(1))
    await user.clear(searchbox())
    await user.type(searchbox(), 'perfect')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(titlesOnPage()).toEqual(['Perfect', 'perfect ']))
    expect(slowSignals[0]?.aborted).toBe(true) // the old request was cancelled
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(titlesOnPage()).toEqual(['Perfect', 'perfect ']) // and nothing overwrote the newer result
  })

  it('still ignores a stale response that resolves after the abort', async () => {
    const user = typing()
    render(<App />)
    await loaded()
    const late = { songs: [makeSong(99, { title: 'STALE' })], page: 1, size: 10, total: 1, total_pages: 1 }
    let releaseStale: () => void = () => {}
    api.intercept((call) => {
      if (call.url.searchParams.get('title') === 'first') {
        // ignores the abort signal on purpose: a response that arrives anyway
        return new Promise<Response>((resolve) => (releaseStale = () => resolve(json(late))))
      }
      return undefined
    })
    await user.type(searchbox(), 'first')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(api.listCalls().at(-1)?.title).toBe('first'))
    await user.clear(searchbox())
    await user.type(searchbox(), 'perfect')
    await act(() => vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS + 50))
    await waitFor(() => expect(titlesOnPage()).toEqual(['Perfect', 'perfect ']))
    await act(async () => releaseStale())
    expect(screen.queryByText('STALE')).not.toBeInTheDocument()
    expect(titlesOnPage()).toEqual(['Perfect', 'perfect '])
  })
})

describe('ratings', () => {
  const ratingSelect = (title: string) => screen.getByLabelText(`Rating for ${title}`) as HTMLSelectElement

  it('offers Unrated and 1 to 5, showing the saved rating', async () => {
    api.songs[1].rating = 4
    render(<App />)
    await loaded()
    expect(within(ratingSelect('Song 0')).getAllByRole('option').map((o) => o.textContent)).toEqual(['Unrated', '1', '2', '3', '4', '5'])
    expect(ratingSelect('Song 0').value).toBe('')
    expect(ratingSelect('Song 1').value).toBe('4')
  })

  it('saves a rating through PUT /songs/{id}/rating and then shows it', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.selectOptions(ratingSelect('Song 2'), '4')
    await waitFor(() => expect(ratingSelect('Song 2').value).toBe('4'))
    const [put] = api.putCalls()
    expect(put.url.pathname).toBe('/songs/id002/rating')
    expect(put.body).toEqual({ rating: 4 })
    expect(api.putCalls()).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('updates an existing rating and leaves other songs alone', async () => {
    api.songs[0].rating = 2
    api.songs[1].rating = 5
    const user = setup()
    render(<App />)
    await loaded()
    await user.selectOptions(ratingSelect('Song 0'), '3')
    await waitFor(() => expect(api.putCalls()).toHaveLength(1))
    await waitFor(() => expect(ratingSelect('Song 0').value).toBe('3'))
    expect(ratingSelect('Song 1').value).toBe('5')
    expect(ratingSelect('Song 2').value).toBe('')
  })

  it('keeps the rating after the page is reloaded from the server', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.selectOptions(ratingSelect('Song 2'), '5')
    await waitFor(() => expect(ratingSelect('Song 2').value).toBe('5'))
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText(/11–20/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /previous page/i }))
    await waitFor(() => expect(screen.getByText(/1–10 of 25/)).toBeInTheDocument())
    expect(ratingSelect('Song 2').value).toBe('5')
  })

  it('disables the control while saving, and shows the new value only after success', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    const held = heldResponse(undefined)
    api.intercept((call) => (call.method === 'PUT' ? held.promise : undefined))
    await user.selectOptions(ratingSelect('Song 2'), '3')
    await waitFor(() => expect(ratingSelect('Song 2')).toBeDisabled())
    expect(ratingSelect('Song 2').value).toBe('') // not shown as saved yet
    expect(screen.getByRole('progressbar', { name: /saving rating for song 2/i })).toBeInTheDocument()
    await act(async () => held.respond(json({ song_id: 'id002', rating: 3 })))
    await waitFor(() => expect(ratingSelect('Song 2')).toBeEnabled())
    expect(ratingSelect('Song 2').value).toBe('3')
  })

  it('shows an error and keeps the old value when the update fails', async () => {
    const user = setup()
    api.songs[2].rating = 2
    render(<App />)
    await loaded()
    api.intercept((call) => (call.method === 'PUT' ? json({ detail: 'Song not found: id002' }, 404) : undefined))
    await user.selectOptions(ratingSelect('Song 2'), '5')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not save the rating for “Song 2”')
    expect(alert).toHaveTextContent('Song not found: id002')
    expect(ratingSelect('Song 2').value).toBe('2') // still the saved rating, not 5
    expect(ratingSelect('Song 2')).toBeEnabled()
  })

  it('shows an error and stays unrated when the network fails', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    api.intercept((call) => (call.method === 'PUT' ? Promise.reject(new TypeError('Failed to fetch')) : undefined))
    await user.selectOptions(ratingSelect('Song 4'), '1')
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save the rating for “song 4”.*could not reach the api/i)
    expect(ratingSelect('Song 4').value).toBe('')
  })

  it('cannot "unrate" a rated song, because the backend has no way to clear a rating', async () => {
    api.songs[0].rating = 3
    render(<App />)
    await loaded()
    const options = within(ratingSelect('Song 0')).getAllByRole('option') as HTMLOptionElement[]
    expect(options.find((o) => o.textContent === 'Unrated')?.disabled).toBe(true)
    const unratedSong = within(ratingSelect('Song 1')).getAllByRole('option') as HTMLOptionElement[]
    expect(unratedSong.find((o) => o.textContent === 'Unrated')?.disabled).toBe(false)
  })

  it('reloads the order after a rating changes while sorted by rating', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.click(within(header(/rating/i)).getByRole('button'))
    await waitFor(() => expect(api.listCalls().at(-1)).toMatchObject({ sort_by: 'rating', order: 'asc' }))
    await waitFor(() => expect(header(/rating/i)).toHaveAttribute('aria-sort', 'ascending'))
    const before = api.listCalls().length
    await user.selectOptions(ratingSelect('Song 0'), '5')
    await waitFor(() => expect(api.listCalls().length).toBe(before + 1))
    expect(api.listCalls().at(-1)).toEqual({ page: '1', size: '10', sort_by: 'rating', order: 'asc' })
    await waitFor(() => expect(ratingSelect('Song 0').value).toBe('5'))
  })

  it('does not reload the page after rating when not sorting by rating', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    const before = api.listCalls().length
    await user.selectOptions(ratingSelect('Song 2'), '4')
    await waitFor(() => expect(ratingSelect('Song 2').value).toBe('4'))
    expect(api.listCalls()).toHaveLength(before)
  })
})

describe('CSV export', () => {
  it('exports the displayed page, in its displayed order, with the displayed columns', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.click(within(header(/tempo/i)).getByRole('button')) // ascending: Song 24 first
    await waitFor(() => expect(titlesOnPage()[0]).toBe('Song 24'))
    await user.click(screen.getByRole('button', { name: /export/i }))
    expect(downloadCsv).toHaveBeenCalledTimes(1)
    const lines = vi.mocked(downloadCsv).mock.calls[0][0].split('\r\n')
    expect(lines[0]).toBe('title,tempo,danceability,energy,mood,duration_ms,valence,rating')
    expect(lines).toHaveLength(10 + 2) // header + 10 rows + trailing newline
    expect(lines.slice(1, 4).map((l) => l.split(',')[0])).toEqual(['Song 24', 'Song 23', 'Song 22'])
    expect(lines[1]).toBe('Song 24,176,0.5,0.1,0,224000,0.4,') // raw values, empty field for the missing rating
    expect(vi.mocked(downloadCsv).mock.calls[0][0]).not.toContain('id024')
  })

  it('exports only the current page', async () => {
    const user = setup()
    render(<App />)
    await loaded()
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText(/21–25|11–20/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(screen.getByText(/21–25 of 25/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /export/i }))
    const lines = vi.mocked(downloadCsv).mock.calls[0][0].split('\r\n')
    expect(lines).toHaveLength(5 + 2)
    expect(lines[1].startsWith('Song 20,')).toBe(true)
  })

  it('writes nulls as empty fields and escapes awkward titles', async () => {
    api.songs[0].title = 'Hello, "World"\nPart 2'
    const user = setup()
    render(<App />)
    await loaded()
    await user.click(screen.getByRole('button', { name: /export/i }))
    const csv = vi.mocked(downloadCsv).mock.calls[0][0]
    expect(csv).toContain('"Hello, ""World""\nPart 2",200,')
    expect(csv).toContain(',,0.5,,1,,,\r\n') // the song with null title/tempo/energy/duration/valence/rating
  })

  it('includes current ratings and is disabled until there is something to export', async () => {
    api.songs[0].rating = 5
    const held = heldResponse(undefined)
    api.intercept(() => held.promise)
    const user = setup()
    render(<App />)
    expect(screen.getByRole('button', { name: /export/i })).toBeDisabled()
    await act(async () => held.respond(json(makePage(api.songs.slice(0, 10), 1, 25))))
    await loaded()
    await user.click(screen.getByRole('button', { name: /export/i }))
    expect(vi.mocked(downloadCsv).mock.calls[0][0].split('\r\n')[1].endsWith(',5')).toBe(true)
  })
})
