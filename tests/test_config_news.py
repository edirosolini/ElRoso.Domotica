"""Los medios de los que salen los titulares, y la economía del resumen."""

import pytest

from homeauto.config import Config, ConfigError

BASE = """
TELEGRAM_TOKEN=1234:abcd
CAST_DEVICES=parlante:d17e8311-d82e-5116-8f58-6292603bbc1b
"""


def write(tmp_path, extra=""):
    path = tmp_path / "domotica.env"
    path.write_text(BASE + extra, encoding="utf-8")
    return path


def test_without_feeds_the_news_are_off(tmp_path):
    config = Config.from_file(write(tmp_path))

    assert config.news_feeds == {}
    assert config.news_enabled is False


def test_one_key_per_outlet(tmp_path):
    """Igual que los calendarios y los Seq: una lista por comas sería ambigua
    porque las URLs traen `:` y `/` propios."""
    config = Config.from_file(
        write(
            tmp_path,
            "NEWS_RSS_INFOBAE=https://www.infobae.com/rss\n"
            "NEWS_RSS_AMBITO=https://www.ambito.com/rss/pages/home.xml\n",
        )
    )

    assert config.news_feeds == {
        "infobae": "https://www.infobae.com/rss",
        "ambito": "https://www.ambito.com/rss/pages/home.xml",
    }
    assert config.news_enabled is True


def test_a_feed_that_is_not_a_url_fails_at_boot(tmp_path):
    with pytest.raises(ConfigError, match="NEWS_RSS_INFOBAE"):
        Config.from_file(write(tmp_path, "NEWS_RSS_INFOBAE=infobae.com/rss\n"))


def test_how_many_headlines_has_a_default_and_a_ceiling(tmp_path):
    assert Config.from_file(write(tmp_path)).news_count == 5
    assert Config.from_file(write(tmp_path, "NEWS_COUNT=3\n")).news_count == 3

    with pytest.raises(ConfigError, match="NEWS_COUNT"):
        Config.from_file(write(tmp_path, "NEWS_COUNT=40\n"))
    with pytest.raises(ConfigError, match="NEWS_COUNT"):
        Config.from_file(write(tmp_path, "NEWS_COUNT=cinco\n"))


def test_the_economy_is_on_unless_it_is_turned_off(tmp_path):
    assert Config.from_file(write(tmp_path)).economy_enabled is True
    assert Config.from_file(write(tmp_path, "ECONOMY=off\n")).economy_enabled is False
    assert Config.from_file(write(tmp_path, "ECONOMY=no\n")).economy_enabled is False
    assert Config.from_file(write(tmp_path, "ECONOMY=on\n")).economy_enabled is True
