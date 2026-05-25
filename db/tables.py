from sqlalchemy import Table, Column, Integer, Text, MetaData
from sqlalchemy.dialects.postgresql import ARRAY

from utils.constants import MovieColumns, MOVIES_TABLE
metadata = MetaData()

movies_table = Table(MOVIES_TABLE,
      metadata,
      Column(MovieColumns.MOVIE_ID, Integer, primary_key=True),
      Column(MovieColumns.TITLE, Text, nullable=False),
      Column(MovieColumns.RELEASE_YEAR, Integer),
      Column(MovieColumns.GENRES, ARRAY(Text))
  )