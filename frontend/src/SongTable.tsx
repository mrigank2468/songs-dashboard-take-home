import { Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TableSortLabel } from '@mui/material'
import type { Song, SortField, SortOrder } from './api'
import { COLUMNS } from './columns'
import { formatDuration, formatNumber, NO_VALUE } from './format'
import { RatingSelect } from './RatingSelect'

interface Props {
  songs: Song[]
  sortBy: SortField | null
  order: SortOrder
  savingIds: ReadonlySet<string>
  emptyMessage: string
  onSort: (field: SortField) => void
  onRate: (song: Song, rating: number) => void
}

export function SongTable({ songs, sortBy, order, savingIds, emptyMessage, onSort, onRate }: Props) {
  return (
    <TableContainer>
      <Table size="small" aria-label="Songs">
        <TableHead>
          <TableRow>
            {COLUMNS.map((column) => {
              const active = sortBy === column.field
              return (
                <TableCell
                  key={column.field}
                  align={column.numeric ? 'right' : 'left'}
                  sortDirection={active ? order : false}
                >
                  <TableSortLabel active={active} direction={active ? order : 'asc'} onClick={() => onSort(column.field)}>
                    {column.label}
                  </TableSortLabel>
                </TableCell>
              )
            })}
          </TableRow>
        </TableHead>
        <TableBody>
          {songs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={COLUMNS.length} align="center">
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            songs.map((song) => (
              <TableRow key={song.id} hover>
                <TableCell>{song.title ?? NO_VALUE}</TableCell>
                <TableCell align="right">{formatNumber(song.tempo)}</TableCell>
                <TableCell align="right">{formatNumber(song.danceability)}</TableCell>
                <TableCell align="right">{formatNumber(song.energy)}</TableCell>
                <TableCell align="right">{formatNumber(song.mood)}</TableCell>
                <TableCell align="right">{formatDuration(song.duration_ms)}</TableCell>
                <TableCell align="right">{formatNumber(song.valence)}</TableCell>
                <TableCell align="right">
                  <RatingSelect
                    title={song.title ?? 'untitled song'}
                    rating={song.rating}
                    saving={savingIds.has(song.id)}
                    onChange={(rating) => onRate(song, rating)}
                  />
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </TableContainer>
  )
}
