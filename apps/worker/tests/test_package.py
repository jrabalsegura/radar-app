from aemet_radar import __version__


def test_package_exposes_a_version() -> None:
    assert __version__ == "0.9.0"
