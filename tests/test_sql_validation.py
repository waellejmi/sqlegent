import sys

sys.path.append("/home/wael/Code/sql-agent/src")
from tools.database import validate_sql

sql_query = "SELECT Artist.Name AS artist_name, SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) AS total_revenue, SUM(InvoiceLine.Quantity) AS total_tracks_sold FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId JOIN Track ON Album.AlbumId = Track.AlbumId JOIN InvoiceLine ON Track.TrackId = InvoiceLine.TrackId GROUP BY Artist.ArtistId ORDER BY total_revenue DESC LIMIT 5;"


if not validate_sql(sql_query, dialect=("postgressql")):
    print(
        "Failed the static check. Only SELECT and WITH statements are allowed. No multiple statements allowed."
    )
