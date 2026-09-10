"""Los titulares del día: escritos enteros al chat, hablados sin un dígito."""

from homeauto.news import NewsClient, MAX_SPOKEN

INFOBAE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Infobae</title>
  <item><title>Cerró la paritaria con un aumento del 12%</title></item>
  <item><title><![CDATA[El dólar tocó los $1.535]]></title></item>
  <item><title>  Vuelve el tren a Mar del Plata  </title></item>
</channel></rss>""".encode("utf-8")

AMBITO = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>Suba de tasas en el mercado</title></item>
  <item><title>Récord de exportaciones</title></item>
</channel></rss>""".encode("utf-8")


def feeds_of(**bodies):
    def fetch(url):
        for alias, body in bodies.items():
            if alias in url:
                if isinstance(body, Exception):
                    raise body
                return body
        raise AssertionError(f"nadie pidió {url}")

    return fetch


def both():
    return {"infobae": "https://infobae/rss", "ambito": "https://ambito/rss"}


def test_headlines_come_from_every_feed():
    news = NewsClient(both(), fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO), count=5)

    titles = [headline.title for headline in news.headlines()]

    assert "Suba de tasas en el mercado" in titles
    assert "Cerró la paritaria con un aumento del 12%" in titles


def test_the_feeds_take_turns_instead_of_one_filling_the_list():
    """Cinco titulares de un solo medio no son las noticias del día."""
    news = NewsClient(both(), fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO), count=4)

    sources = [headline.source for headline in news.headlines()]

    assert sources == ["infobae", "ambito", "infobae", "ambito"]


def test_a_feed_that_falls_does_not_take_the_others_down():
    news = NewsClient(
        both(), fetch=feeds_of(infobae=OSError("timeout"), ambito=AMBITO), count=5
    )

    assert [headline.source for headline in news.headlines()] == ["ambito", "ambito"]


def test_a_feed_without_a_declared_charset_is_still_read_right():
    """🔴 Ámbito contesta sin charset en el header: con `response.text`,
    requests adivina latin-1 y "Envíos" llega al chat como "EnvÃ­os"."""
    body = '<rss><channel><item><title>Envíos de oro</title></item></channel></rss>'
    news = NewsClient({"x": "https://x/rss"}, fetch=lambda url: body.encode("utf-8"))

    assert news.headlines()[0].title == "Envíos de oro"


def test_titles_arrive_clean():
    news = NewsClient({"infobae": "https://infobae/rss"}, fetch=feeds_of(infobae=INFOBAE))

    titles = [headline.title for headline in news.headlines()]

    assert "El dólar tocó los $1.535" in titles, "el CDATA no es parte del titular"
    assert "Vuelve el tren a Mar del Plata" in titles, "sin espacios de más"


def test_the_written_half_keeps_the_digits_and_names_the_source():
    news = NewsClient(both(), fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO), count=2)

    digest = news.digest()

    assert "12%" in digest.written
    assert "Infobae" in digest.written or "infobae" in digest.written


def test_the_spoken_half_is_what_the_model_gave_back():
    news = NewsClient(
        both(),
        fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO),
        speak=lambda prompt: "Cerró la paritaria con un aumento del doce por ciento.",
        count=2,
    )

    assert news.digest().spoken.startswith("Cerró la paritaria")


def test_a_spoken_half_with_digits_is_thrown_away():
    """🔴 Igual que en las preguntas: si la voz no se puede confiar, no se habla.

    Lo escrito nunca se pierde, así que el chat sigue teniendo los titulares.
    """
    news = NewsClient(
        both(),
        fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO),
        speak=lambda prompt: "El dólar tocó los 1535 pesos.",
    )

    digest = news.digest()

    assert digest.spoken == ""
    assert "1.535" in digest.written


def test_a_spoken_half_that_rambles_is_thrown_away():
    news = NewsClient(
        both(),
        fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO),
        speak=lambda prompt: "muy largo " * MAX_SPOKEN,
    )

    assert news.digest().spoken == ""


def test_without_a_model_there_is_nothing_to_say_out_loud():
    """Sin clave del modelo los titulares no se pueden decir sin dígitos."""
    news = NewsClient(both(), fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO))

    digest = news.digest()

    assert digest.spoken == ""
    assert digest.written


def test_a_model_that_breaks_costs_the_voice_and_nothing_more():
    def broken(prompt):
        raise RuntimeError("se cayó")

    news = NewsClient(
        both(), fetch=feeds_of(infobae=INFOBAE, ambito=AMBITO), speak=broken
    )

    digest = news.digest()

    assert digest.spoken == ""
    assert digest.written


def test_no_feeds_at_all_is_an_empty_digest():
    news = NewsClient({}, fetch=feeds_of())

    digest = news.digest()

    assert digest.written == ""
    assert digest.spoken == ""
