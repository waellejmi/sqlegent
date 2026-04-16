from sqlalchemy import create_engine, text

engine_url = "sqlite:////home/wael/Code/sql-agent/.app_cache/context_layer.sqlite"

engine = create_engine(engine_url)

with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT id,project_id,db_fingerprint,question,question_norm,sql,tables_json,created_at FROM 'query_memory';"
        )
    )
    for row in result:
        print(row)

"""
SELECT Track.Name, SUM(InvoiceLine.Quantity) AS TotalQuantity FROM InvoiceLine JOIN Track ON InvoiceLine.TrackId = Track.TrackId GROUP BY Track.TrackId ORDER BY TotalQuantity DESC LIMIT 4;

SELECT Track.Name, SUM(InvoiceLine.Quantity) AS TotalQuantity, MediaType.Name AS MediaType, Genre.Name AS Genre FROM InvoiceLine JOIN Track ON InvoiceLine.TrackId = Track.TrackId JOIN MediaType ON Track.MediaTypeId = MediaType.MediaTypeId JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Track.TrackId ORDER BY TotalQuantity DESC LIMIT 4;

SELECT c.CustomerId, c.FirstName, c.LastName, SUM(i.Total) AS TotalSpent FROM Invoice i JOIN Customer c ON i.CustomerId = c.CustomerId GROUP BY c.CustomerId HAVING SUM(i.Total) > (SELECT AVG(TotalSpent) FROM (SELECT SUM(Total) AS TotalSpent FROM Invoice GROUP BY CustomerId)) ORDER BY TotalSpent DESC LIMIT 5;

SELECT c.CustomerId, c.FirstName, c.LastName, SUM(i.Total) AS TotalSpent FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId GROUP BY c.CustomerId HAVING SUM(i.Total) > (SELECT AVG(TotalSpent) FROM (SELECT SUM(Total) AS TotalSpent FROM Invoice GROUP BY CustomerId)) ORDER BY TotalSpent DESC LIMIT 5;

which customers spent more than the average customer spending, and what is their total amount spent?
which customers spent more than the average customer spending, and what is their total amount spent?

SELECT Artist.Name, SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) AS TotalRevenue, SUM(InvoiceLine.Quantity) AS TotalTracksSold FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId JOIN Track ON Album.AlbumId = Track.AlbumId JOIN InvoiceLine ON Track.TrackId = InvoiceLine.TrackId GROUP BY Artist.ArtistId ORDER BY TotalRevenue DESC LIMIT 5;

SELECT Artist.Name, SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) AS TotalRevenue, SUM(InvoiceLine.Quantity) AS TotalTracksSold FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId JOIN Track ON Album.AlbumId = Track.AlbumId JOIN InvoiceLine ON Track.TrackId = InvoiceLine.TrackId GROUP BY Artist.ArtistId, Artist.Name ORDER BY TotalRevenue DESC, TotalTracksSold DESC, Artist.Name ASC LIMIT 5;
"""
