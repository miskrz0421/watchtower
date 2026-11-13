# Fake listings server

A tiny flat-rental website for Watchtower demos. It needs nothing but the standard library.

```bash
uv run watchtower-fake-listings            # http://127.0.0.1:8000
uv run watchtower-fake-listings --port 8001 --data my_listings.json
```

| Path | Content |
|---|---|
| `/listings` | HTML page, one `div.offer` per listing |
| `/listings.json` | the listings as JSON |
| `/feed.xml` | RSS 2.0 feed, one entry per listing |
| `/flats/<id>` | page of one listing (target of the title links) |

The server reads `listings.json` again on every request. To simulate a new offer, add an entry
to the file while the server runs; the next check sees it. If the file is not valid JSON (for
example half-way through editing), the server answers `500`, like a broken real site.

Each offer on `/listings` follows the HTML contract used by `WebPageSource`:

```html
<div class="offer" data-id="1">
  <a class="title" href="/flats/1">Flat Stare Miasto</a>
  <span class="price">3 500 zł</span>
</div>
```

The matching source:

```python
WebPageSource(
    url="http://127.0.0.1:8000/listings",
    selector=".offer",
    title_selector=".title",
    price_selector=".price",
    key_attribute="data-id",
)
```
