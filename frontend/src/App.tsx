import {
  Alert,
  Box,
  Button,
  Container,
  LinearProgress,
  Paper,
  Snackbar,
  TablePagination,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useRef, useState } from 'react'
import { fetchSongs, PAGE_SIZE, putRating } from './api'
import type { Song, SongPage, SongsQuery, SortField } from './api'
import { downloadCsv, toCsv } from './csv'
import { SongTable } from './SongTable'
import './App.css'

export const SEARCH_DEBOUNCE_MS = 300

const INITIAL_QUERY: SongsQuery = { page: 1, sortBy: null, order: 'asc', title: '' }

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error))

export default function App() {
  // Everything the request depends on lives in one object, so one change is one request.
  const [query, setQuery] = useState<SongsQuery>(INITIAL_QUERY)
  const [searchInput, setSearchInput] = useState('')
  const [data, setData] = useState<SongPage | null>(null) // the last page loaded successfully
  const [reloadKey, setReloadKey] = useState(0)
  const [savingIds, setSavingIds] = useState<ReadonlySet<string>>(new Set())
  const [notice, setNotice] = useState<string | null>(null)
  const queryRef = useRef(query)
  useEffect(() => {
    queryRef.current = query
  })

  // `settled` records which request last finished (and how). We are loading exactly when the
  // current request is not the one that settled, so there is no separate loading flag to keep in sync.
  const requestKey = `${JSON.stringify(query)}#${reloadKey}`
  const [settled, setSettled] = useState<{ key: string; error: string | null } | null>(null)
  const loading = settled?.key !== requestKey
  const error = settled?.key === requestKey ? settled.error : null

  // Load whenever the query changes. Cleanup aborts the previous request, and a response
  // that arrives after that is ignored, so a slow old request can never overwrite a newer one.
  useEffect(() => {
    const controller = new AbortController()
    fetchSongs(query, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        if (result.songs.length === 0 && result.total > 0 && result.page > result.total_pages) {
          // The page we asked for no longer exists (e.g. the data changed): go to the last real one.
          setQuery((q) => ({ ...q, page: result.total_pages }))
          return
        }
        setData(result)
        setSettled({ key: requestKey, error: null })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setData(null)
        setSettled({ key: requestKey, error: messageOf(err) })
      })
    return () => controller.abort()
  }, [query, reloadKey, requestKey])

  // Debounce the search box: after 300 ms without typing, apply the trimmed text and go to
  // page 1 in the same update (so it is one request, not "old page, then page 1").
  useEffect(() => {
    const timer = setTimeout(() => {
      const title = searchInput.trim()
      setQuery((q) => (q.title === title ? q : { ...q, title, page: 1 }))
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  const handleSort = (field: SortField) =>
    setQuery((q) => ({
      ...q,
      sortBy: field,
      order: q.sortBy === field && q.order === 'asc' ? 'desc' : 'asc', // new column starts ascending
      page: 1,
    }))

  const handleRate = async (song: Song, rating: number) => {
    setSavingIds((ids) => new Set(ids).add(song.id))
    try {
      const saved = await putRating(song.id, rating)
      setData((d) => d && { ...d, songs: d.songs.map((s) => (s.id === saved.song_id ? { ...s, rating: saved.rating } : s)) })
      // The row order is stale once the rating changes while sorting by rating: reload it.
      if (queryRef.current.sortBy === 'rating') setReloadKey((k) => k + 1)
    } catch (err) {
      setNotice(`Could not save the rating for “${song.title ?? 'untitled song'}”: ${messageOf(err)}`)
    } finally {
      setSavingIds((ids) => {
        const next = new Set(ids)
        next.delete(song.id)
        return next
      })
    }
  }

  const emptyMessage = query.title ? `No songs with the title “${query.title}”.` : 'No songs found.'

  return (
    <Container maxWidth="lg" className="app">
      <Typography variant="h4" component="h1" gutterBottom>
        Songs dashboard
      </Typography>

      <Box className="toolbar">
        <TextField
          label="Search by title"
          helperText="Exact title, ignoring case and extra spaces"
          size="small"
          type="search"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          className="search"
        />
        <Button variant="outlined" onClick={() => data && downloadCsv(toCsv(data.songs))} disabled={!data || data.songs.length === 0}>
          Export this page (CSV)
        </Button>
      </Box>

      {error && (
        <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => setReloadKey((k) => k + 1)}>Retry</Button>}>
          {error}
        </Alert>
      )}

      {!error && (
        <Paper variant="outlined" aria-busy={loading}>
          {loading && <LinearProgress aria-label="Loading songs" />}
          {data ? (
            <>
              <div className={loading ? 'table-wrap loading' : 'table-wrap'}>
                <SongTable
                  songs={data.songs}
                  sortBy={query.sortBy}
                  order={query.order}
                  savingIds={savingIds}
                  emptyMessage={emptyMessage}
                  onSort={handleSort}
                  onRate={handleRate}
                />
              </div>
              <TablePagination
                component="div"
                count={data.total}
                page={Math.max(0, Math.min(query.page - 1, Math.ceil(data.total / PAGE_SIZE) - 1))}
                rowsPerPage={PAGE_SIZE}
                rowsPerPageOptions={[]}
                onPageChange={(_, page) => setQuery((q) => ({ ...q, page: page + 1 }))}
                labelDisplayedRows={({ from, to, count }) =>
                  count === 0 ? '0 songs' : `${from}–${to} of ${count} · page ${data.page} of ${data.total_pages}`
                }
              />
            </>
          ) : (
            <Box className="placeholder" />
          )}
        </Paper>
      )}

      <Snackbar open={notice !== null} autoHideDuration={8000} onClose={() => setNotice(null)}>
        <Alert severity="error" onClose={() => setNotice(null)} variant="filled">
          {notice}
        </Alert>
      </Snackbar>
    </Container>
  )
}
