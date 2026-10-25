import { CircularProgress, Select } from '@mui/material'
import type { ChangeEvent } from 'react'

const RATINGS = [1, 2, 3, 4, 5]

interface Props {
  title: string
  rating: number | null
  saving: boolean
  onChange: (rating: number) => void
}

/**
 * A 1-5 dropdown. "Unrated" shows the empty state; the backend cannot remove a rating
 * (PUT takes 1-5 only), so once a song is rated that option is disabled, not faked.
 * The shown value is always the saved one: it only changes after the API confirms.
 */
export function RatingSelect({ title, rating, saving, onChange }: Props) {
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    if (event.target.value !== '') onChange(Number(event.target.value))
  }
  return (
    <span className="rating-cell">
      <Select
        native
        size="small"
        value={rating ?? ''}
        onChange={handleChange as never}
        disabled={saving}
        inputProps={{ 'aria-label': `Rating for ${title}` }}
      >
        <option value="" disabled={rating !== null}>
          Unrated
        </option>
        {RATINGS.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </Select>
      {saving && <CircularProgress size={16} aria-label={`Saving rating for ${title}`} />}
    </span>
  )
}
