import type { Song, SortField } from './api'

export interface Column {
  field: SortField
  label: string
  numeric: boolean
}

/** The displayed columns, in order. The song id is deliberately not one of them. */
export const COLUMNS: Column[] = [
  { field: 'title', label: 'Title', numeric: false },
  { field: 'tempo', label: 'Tempo (BPM)', numeric: true },
  { field: 'danceability', label: 'Danceability', numeric: true },
  { field: 'energy', label: 'Energy', numeric: true },
  { field: 'mood', label: 'Mood', numeric: true },
  { field: 'duration_ms', label: 'Duration', numeric: true },
  { field: 'valence', label: 'Valence', numeric: true },
  { field: 'rating', label: 'Rating', numeric: true },
]

export type ColumnValue = Song[SortField]
