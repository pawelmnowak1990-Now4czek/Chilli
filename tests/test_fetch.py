"""Step 5: fetching the content behind a link, with the network replaced (httpx.MockTransport)."""

import httpx
import pytest

from app import fetch

ARTICLE_HTML = """<html><head><title>Funkcje okna w SQL</title></head><body>
<nav>Menu Strona główna Kontakt</nav>
<article><h1>Funkcje okna w SQL</h1>
<p>ROW_NUMBER() numeruje wiersze w obrębie partycji. To jedna z najprzydatniejszych funkcji
w codziennej pracy analityka, bo pozwala wybrać najnowszy rekord dla każdego klienta.</p>
<p>Drugi akapit opisuje LAG i LEAD, które sięgają do poprzedniego i następnego wiersza,
co ułatwia liczenie zmian dzień do dnia bez samozłączeń tabeli.</p></article>
<footer>Stopka © 2026</footer></body></html>"""

FX_JSON = {"code": 200, "tweet": {"text": "Pełny, długi post\nz wieloma liniami", "author": {"name": "Nauczymy Cię AI", "screen_name": "nauczymycieAI"}}}

OEMBED_JSON = {"author_name": "Nauczymy Cię AI", "html": '<blockquote><p lang="pl">Początek posta<br>druga linia &amp; więcej… <a href="https://t.co/x">pic</a></p>&mdash; autor</blockquote>'}


def make_client(routes: dict[str, httpx.Response]) -> httpx.Client:
    """A client that answers from a table instead of the network: host -> response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(request.url.host, httpx.Response(404))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_artykul_bez_menu_i_stopki() -> None:
    client = make_client({"example.com": httpx.Response(200, text=ARTICLE_HTML)})
    page = fetch.fetch("https://example.com/sql", client=client)
    assert "ROW_NUMBER()" in page.text and "LAG i LEAD" in page.text
    assert "Stopka" not in page.text
    assert page.title == "Funkcje okna w SQL"


def test_artykul_zachowuje_naglowki_i_listy() -> None:
    # Content is saved as Markdown: subheadings and list items stay readable for AI and people.
    html = """<html><head><title>Okna</title></head><body><article><h1>Okna</h1>
    <p>Wstęp o funkcjach okna, który jest na tyle długi, żeby uznać go za prawdziwy akapit artykułu.</p>
    <h2>Najważniejsze funkcje</h2>
    <ul><li>ROW_NUMBER numeruje wiersze w partycji</li><li>LAG sięga do poprzedniego wiersza</li></ul>
    <p>Zakończenie z podsumowaniem całości, też dostatecznie długie, żeby zostało w tekście.</p>
    </article></body></html>"""
    client = make_client({"example.com": httpx.Response(200, text=html)})
    text = fetch.fetch("https://example.com/okna", client=client).text
    assert "## Najważniejsze funkcje" in text
    assert "- ROW_NUMBER numeruje wiersze w partycji" in text


def test_ukosniki_w_kodzie_zostaja() -> None:
    html = r"""<html><body><article><h1>Regex</h1><p>Akapit o wyrażeniach regularnych, wystarczająco długi,
    żeby trafilatura uznała go za treść artykułu i go nie pominęła.</p>
    <pre><code>SELECT regexp_replace(a, '\d+\.\d+', '') FROM t_tab</code></pre>
    <p>Tekst z nazwą ROW_NUMBER, gwiazdką * i ścieżką C:\temp\a_b, też dość długi, żeby został.</p>
    </article></body></html>"""
    client = make_client({"example.com": httpx.Response(200, text=html)})
    text = fetch.fetch("https://example.com/regex", client=client).text
    assert r"'\d+\.\d+'" in text and "t_tab" in text
    assert "ROW_NUMBER" in text and r"C:\temp\a_b" in text


def test_strona_404_to_blad() -> None:
    client = make_client({})
    with pytest.raises(fetch.FetchError, match="HTTP 404"):
        fetch.fetch("https://example.com/nie-ma", client=client)


def test_post_z_x_przez_fxtwitter() -> None:
    client = make_client({"api.fxtwitter.com": httpx.Response(200, json=FX_JSON)})
    page = fetch.fetch("https://x.com/nauczymycieai/status/123?s=12", client=client)
    assert page.text == FX_JSON["tweet"]["text"]
    assert page.author == "Nauczymy Cię AI (@nauczymycieAI)"


def test_post_z_x_gdy_fxtwitter_nie_dziala_oembed() -> None:
    client = make_client({
        "api.fxtwitter.com": httpx.Response(500),
        "publish.twitter.com": httpx.Response(200, json=OEMBED_JSON),
    })
    page = fetch.fetch("https://twitter.com/user/status/123", client=client)
    assert page.text == "Początek posta\ndruga linia & więcej… pic"
    assert page.author == "Nauczymy Cię AI"


FX_WITH_LINK = {"code": 200, "tweet": {
    "text": "Claude FDE path:\nhttps://example.com/sql",
    "author": {"name": "Dani", "screen_name": "dani"},
    "raw_text": {"facets": [
        {"type": "url", "replacement": "https://example.com/sql"},
        {"type": "url", "replacement": "https://x.com/inny/status/1"},
    ]},
}}


def test_post_z_linkiem_dociaga_tresc_strony() -> None:
    client = make_client({
        "api.fxtwitter.com": httpx.Response(200, json=FX_WITH_LINK),
        "example.com": httpx.Response(200, text=ARTICLE_HTML),
    })
    page = fetch.fetch("https://x.com/dani/status/1", client=client)
    assert page.text.startswith("Claude FDE path:")
    assert "ROW_NUMBER()" in page.text  # linked article content appended below the post
    assert page.title == "Funkcje okna w SQL"


def test_post_z_niedzialajacym_linkiem_zostaje_sam_post() -> None:
    client = make_client({"api.fxtwitter.com": httpx.Response(200, json=FX_WITH_LINK)})
    page = fetch.fetch("https://x.com/dani/status/1", client=client)
    assert page.text == FX_WITH_LINK["tweet"]["text"]


# X Article: the post holds only an x.com/i/article/… link, fxtwitter gives the content
# in the `article` field as blocks (Draft.js editor format). Made-up data, shaped like fxtwitter's.
FX_ARTICLE = {"code": 200, "tweet": {
    "text": "https://x.com/i/article/999",
    "author": {"name": "Rynki", "screen_name": "rynki"},
    "raw_text": {"facets": [{"type": "url", "replacement": "https://x.com/i/article/999"}]},
    "article": {
        "title": "Czy to bańka?",
        "preview_text": "Najczęstsze pytanie",
        "content": {
            "blocks": [
                {"type": "unstyled", "text": "Najczęstsze pytanie: czy AI to bańka?", "entityRanges": []},
                {"type": "header-two", "text": "Ostatnie 45 dni", "entityRanges": []},
                {"type": "atomic", "text": " ", "entityRanges": [{"key": 0, "offset": 0, "length": 1}]},
                {"type": "unordered-list-item", "text": "spadki przez 31 sesji", "entityRanges": []},
                {"type": "nieznany-typ", "text": "Wniosek końcowy.", "entityRanges": []},
            ],
            "entityMap": [{"key": "0", "value": {"type": "MEDIA", "data": {"caption": "Wykres przepływów"}}}],
        },
    },
}}


def test_artykul_x_pelna_tresc_z_blokow() -> None:
    client = make_client({"api.fxtwitter.com": httpx.Response(200, json=FX_ARTICLE)})
    page = fetch.fetch("https://x.com/rynki/status/1?s=12", client=client)
    assert page.title == "Czy to bańka?"
    assert page.author == "Rynki (@rynki)"
    assert page.text.startswith("Czy to bańka?\n\nNajczęstsze pytanie: czy AI to bańka?")
    assert "## Ostatnie 45 dni" in page.text
    assert "[Image: Wykres przepływów]" in page.text
    assert "- spadki przez 31 sesji" in page.text
    assert "Wniosek końcowy." in page.text  # an unknown block type is not lost
    assert "x.com/i/article" not in page.text  # the bare article link adds nothing


def test_artykul_x_z_komentarzem_autora_zostawia_komentarz() -> None:
    data = {"code": 200, "tweet": {**FX_ARTICLE["tweet"], "text": "Ważne, przeczytajcie https://x.com/i/article/999"}}
    client = make_client({"api.fxtwitter.com": httpx.Response(200, json=data)})
    page = fetch.fetch("https://x.com/rynki/status/1", client=client)
    assert page.text.startswith("Ważne, przeczytajcie")
    assert "## Ostatnie 45 dni" in page.text


def test_sam_link_bez_tresci_to_blad() -> None:
    """fxtwitter gave no article, oEmbed returns only a link: better an error (to retry)
    than a save described as "content unavailable"."""
    only_link = {"code": 200, "tweet": {**FX_ARTICLE["tweet"]}}
    del only_link["tweet"]["article"]
    client = make_client({
        "api.fxtwitter.com": httpx.Response(200, json=only_link),
        "publish.twitter.com": httpx.Response(200, json={"html": '<blockquote><p><a href="https://t.co/a">https://t.co/a</a></p></blockquote>'}),
    })
    with pytest.raises(fetch.FetchError, match="only a link"):
        fetch.fetch("https://x.com/rynki/status/1", client=client)


def test_strona_bez_artykulu_bierze_opis_ze_strony() -> None:
    """trafilatura finds no article text: the page description (og:description) is used instead of an error."""
    page_html = """<html><head><title>Kalkulator</title>
    <meta property="og:description" content="Kalkulator marży dla sklepów internetowych z modą."></head>
    <body><div id="app"></div></body></html>"""
    client = make_client({"example.com": httpx.Response(200, text=page_html)})
    page = fetch.fetch("https://example.com/kalkulator", client=client)
    assert "Kalkulator marży" in page.text
    assert page.partial  # a screenshot with this URL keeps its own, more complete text


def test_pelny_artykul_nie_jest_czesciowy() -> None:
    client = make_client({"example.com": httpx.Response(200, text=ARTICLE_HTML)})
    assert not fetch.fetch("https://example.com/sql", client=client).partial


def test_sam_link_gdy_fxtwitter_nie_dziala_to_blad() -> None:
    client = make_client({
        "api.fxtwitter.com": httpx.Response(500),
        "publish.twitter.com": httpx.Response(200, json={"html": '<blockquote><p><a href="https://t.co/a">https://t.co/a</a></p></blockquote>'}),
    })
    with pytest.raises(fetch.FetchError, match="only a link"):
        fetch.fetch("https://x.com/rynki/status/1", client=client)


def test_strona_x_bez_posta_nie_bierze_opisu_z_meta() -> None:
    """An X page other than a post (e.g. a bare article URL) shows only X's generic description without
    logging in: that is not content, so an error rather than a save with that description."""
    page_html = '<html><head><meta property="og:description" content="From breaking news to entertainment"></head><body></body></html>'
    client = make_client({"x.com": httpx.Response(200, text=page_html)})
    with pytest.raises(fetch.FetchError):
        fetch.fetch("https://x.com/i/article/999", client=client)
