"""Step 4: shrinking a screenshot to a WebP copy."""

from pathlib import Path

from PIL import Image

from app import images


def test_duzy_zrzut_zmniejszony_do_webp(tmp_path: Path) -> None:
    source = tmp_path / "zrzut.png"
    Image.new("RGBA", (1290, 2796), (255, 0, 0, 255)).save(source)  # size of an iPhone screenshot

    target = images.shrink_to_webp(source, tmp_path / "kopia.webp")

    with Image.open(target) as result:
        assert result.format == "WEBP"
        assert max(result.size) == 1568
        assert abs(result.size[0] / result.size[1] - 1290 / 2796) < 0.01  # proportions kept


def test_maly_obraz_nie_jest_powiekszany(tmp_path: Path) -> None:
    source = tmp_path / "maly.png"
    Image.new("P", (300, 200)).save(source)  # palette mode, which WebP does not accept directly

    target = images.shrink_to_webp(source, tmp_path / "maly.webp")

    with Image.open(target) as result:
        assert result.size == (300, 200)
