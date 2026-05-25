class MovieColumns:
    MOVIE_ID = "movie_id"
    TITLE = "title"
    RELEASE_YEAR = "release_year"
    GENRES = "genres"

MOVIES_TABLE = "movies"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
INSERTED_KEY = "inserted"
BATCH_SIZE = 500
CSV_TITLE_COL = "title"
CSV_GENRES_COL = "genres"
NO_GENRES_VALUE = "(no genres listed)"
YEAR_EXTRACT_PATTERN = r"\((\d{4})\)$"
YEAR_STRIP_PATTERN = r"\s*\(\d{4}\)\s*$"
CSV_TO_DB_COLUMNS = {"movieId": MovieColumns.MOVIE_ID}
GENRE_SEPARATOR = "|"

