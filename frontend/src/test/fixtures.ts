import type { Song, SongPage } from '../api'

export function makeSong(n: number, overrides: Partial<Song> = {}): Song {
  return {
    id: `id${String(n).padStart(3, '0')}`,
    title: `Song ${n}`,
    danceability: 0.5,
    energy: 0.7,
    mood: n % 2,
    acousticness: 0.1,
    tempo: 120,
    duration_ms: 200_000 + n * 1000,
    num_sections: 8,
    num_segments: 800,
    valence: 0.4,
    rating: null,
    ...overrides,
  }
}

export function makePage(songs: Song[], page = 1, total = songs.length, size = 10): SongPage {
  return { songs, page, size, total, total_pages: Math.ceil(total / size) }
}
