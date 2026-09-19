"""Genera iconos multiplataforma a partir del branding oficial de Aegis."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

SOURCE_LOGO = ASSETS / "aegis-auditor-logo.png"


def _legacy_shield(size: int) -> Image.Image:
    """Fallback si el logo oficial no está disponible."""
    image = Image.new("RGBA", (size, size), (6, 17, 29, 0))
    draw = ImageDraw.Draw(image)

    cx = size // 2
    shield = [
        (cx, int(size * 0.08)),
        (int(size * 0.82), int(size * 0.24)),
        (int(size * 0.75), int(size * 0.66)),
        (cx, int(size * 0.88)),
        (int(size * 0.25), int(size * 0.66)),
        (int(size * 0.18), int(size * 0.24)),
    ]
    draw.polygon(shield, fill=(22, 156, 255, 255))

    inner = [
        (cx, int(size * 0.16)),
        (int(size * 0.70), int(size * 0.29)),
        (int(size * 0.65), int(size * 0.60)),
        (cx, int(size * 0.78)),
        (int(size * 0.35), int(size * 0.60)),
        (int(size * 0.30), int(size * 0.29)),
    ]
    draw.polygon(inner, fill=(11, 31, 47, 255))

    draw.line(
        [
            (int(size * 0.35), int(size * 0.49)),
            (int(size * 0.47), int(size * 0.62)),
            (int(size * 0.69), int(size * 0.36)),
        ],
        fill=(255, 255, 255, 255),
        width=max(4, int(size * 0.07)),
        joint="curve",
    )
    return image


def _official_shield() -> Image.Image | None:
    """Extrae el escudo del wordmark sin usar el texto en iconos pequeños."""
    if not SOURCE_LOGO.exists():
        return None

    source = Image.open(SOURCE_LOGO).convert("RGBA")

    # El logo final es cuadrado: el escudo ocupa la zona superior y el
    # wordmark la inferior. Recortamos sólo la marca gráfica para taskbar,
    # .ico e .icns; el wordmark completo se usa dentro de la aplicación.
    shield_region = source.crop(
        (
            0,
            0,
            source.width,
            int(source.height * 0.70),
        )
    )

    alpha = shield_region.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return None

    return shield_region.crop(bbox)


def build_icon(size: int) -> Image.Image:
    shield = _official_shield()
    if shield is None:
        return _legacy_shield(size)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    max_edge = int(size * 0.90)

    shield.thumbnail(
        (max_edge, max_edge),
        Image.Resampling.LANCZOS,
    )

    x = (size - shield.width) // 2
    y = (size - shield.height) // 2
    canvas.alpha_composite(shield, (x, y))
    return canvas


def main() -> None:
    png = build_icon(1024)
    png.save(ASSETS / "aegis-auditor.png")

    ico_sizes = [
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    ]
    png.save(
        ASSETS / "aegis-auditor.ico",
        format="ICO",
        sizes=ico_sizes,
    )

    png.save(
        ASSETS / "aegis-auditor.icns",
        format="ICNS",
    )


if __name__ == "__main__":
    main()
