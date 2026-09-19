"""Genera iconos multiplataforma de Aegis Auditor sin depender de archivos binarios versionados."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def build_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (6, 17, 29, 255))
    draw = ImageDraw.Draw(image)

    cx = size // 2
    top = int(size * 0.10)
    left = int(size * 0.20)
    right = int(size * 0.80)
    lower = int(size * 0.80)
    mid_y = int(size * 0.52)

    shield = [
        (cx, top),
        (right, int(size * 0.25)),
        (int(size * 0.74), int(size * 0.62)),
        (cx, lower),
        (int(size * 0.26), int(size * 0.62)),
        (left, int(size * 0.25)),
    ]
    draw.polygon(shield, fill=(22, 156, 255, 255))

    inner = [
        (cx, int(size * 0.18)),
        (int(size * 0.70), int(size * 0.30)),
        (int(size * 0.66), int(size * 0.58)),
        (cx, int(size * 0.72)),
        (int(size * 0.34), int(size * 0.58)),
        (int(size * 0.30), int(size * 0.30)),
    ]
    draw.polygon(inner, fill=(11, 31, 47, 255))

    width = max(4, int(size * 0.07))
    draw.line(
        [
            (int(size * 0.36), mid_y),
            (int(size * 0.47), int(size * 0.63)),
            (int(size * 0.68), int(size * 0.38)),
        ],
        fill=(255, 255, 255, 255),
        width=width,
        joint="curve",
    )
    return image


def main() -> None:
    png = build_icon(1024)
    png.save(ASSETS / "aegis-auditor.png")

    ico_sizes = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]
    png.save(
        ASSETS / "aegis-auditor.ico",
        format="ICO",
        sizes=ico_sizes,
    )

    # Pillow escribe ICNS con múltiples representaciones a partir de la imagen grande.
    png.save(ASSETS / "aegis-auditor.icns", format="ICNS")


if __name__ == "__main__":
    main()
