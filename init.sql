CREATE TABLE IF NOT EXISTS movies (
      movie_id     INTEGER PRIMARY KEY,
      title        TEXT NOT NULL,
      release_year INTEGER,
      genres       TEXT[]
  );

CREATE INDEX IF NOT EXISTS idx_genres ON movies USING GIN (genres);
CREATE INDEX IF NOT EXISTS idx_release_year ON movies (release_year);