"""Utility helpers, including the CSV processor for bulk movie ingestion."""
import logging
from abc import ABC, abstractmethod
import pandas as pd
import io
from utils.constants import (
    CSV_TO_DB_COLUMNS, MovieColumns, CSV_TITLE_COL, CSV_GENRES_COL,
    YEAR_EXTRACT_PATTERN, YEAR_STRIP_PATTERN, NO_GENRES_VALUE, GENRE_SEPARATOR,
)

logger = logging.getLogger(__name__)


class FileProcessorHelper(ABC):
    @abstractmethod
    def process(self, file_bytes: bytes) -> list[dict]:
        pass


class CSVProcessorHelper(FileProcessorHelper):
    def process(self, file_bytes: bytes) -> list[dict]:
        df = pd.read_csv(io.BytesIO(file_bytes))
        df.columns = df.columns.str.strip()
        df = df.rename(columns=CSV_TO_DB_COLUMNS)
        df[MovieColumns.RELEASE_YEAR] = df[CSV_TITLE_COL].str.extract(YEAR_EXTRACT_PATTERN).astype("Int64")
        df[MovieColumns.TITLE] = df[CSV_TITLE_COL].str.replace(YEAR_STRIP_PATTERN, "", regex=True).str.strip()
        df[MovieColumns.GENRES] = df[CSV_GENRES_COL].apply(
            lambda g: None if g == NO_GENRES_VALUE else [genre.strip().title() for genre in g.split(GENRE_SEPARATOR)]
        )
        df = df.dropna(subset=[MovieColumns.MOVIE_ID])
        records = df.to_dict(orient="records")
        logger.debug("CSV parsed: %d records", len(records))
        return records
