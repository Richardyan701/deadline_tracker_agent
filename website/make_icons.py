"""Draw Groot's app icon: a white tree on Groot's green. Needs Pillow (pip install pillow).

    python website/make_icons.py

Writes the icons the website uses (website/icons/) and the tab icon for the
laptop version (web/static/icon-32.png). Each icon is drawn 4 times bigger,
then shrunk, so the edges are smooth.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
GREEN = (46, 107, 74)  # --green in groot.css
WHITE = (255, 255, 255)


def tree(size: int, rounded: bool, scale: float) -> Image.Image:
    """The icon at size x size pixels. scale shrinks the tree, so a "maskable" icon keeps it in the safe middle."""
    big = size * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * 0.22, fill=GREEN)
    else:
        draw.rectangle([0, 0, big, big], fill=GREEN)  # the phone cuts its own shape out of this

    def at(x, y):  # a point given as a share of the icon, around the middle
        return big / 2 + (x - 0.5) * big * scale, big / 2 + (y - 0.5) * big * scale

    def circle(x, y, r):
        cx, cy = at(x, y)
        r *= big * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)

    # The trunk, then three round clumps of leaves
    left, top = at(0.455, 0.52)
    right, bottom = at(0.545, 0.84)
    draw.rounded_rectangle([left, top, right, bottom], radius=big * scale * 0.02, fill=WHITE)
    circle(0.5, 0.33, 0.19)
    circle(0.33, 0.5, 0.15)
    circle(0.67, 0.5, 0.15)
    circle(0.5, 0.52, 0.15)
    return image.resize((size, size), Image.LANCZOS)


def main():
    icons = ROOT / "website" / "icons"
    icons.mkdir(exist_ok=True)
    tree(32, True, 0.9).save(icons / "icon-32.png")
    tree(192, True, 0.9).save(icons / "icon-192.png")
    tree(512, True, 0.9).save(icons / "icon-512.png")
    tree(512, False, 0.62).save(icons / "icon-maskable-512.png")
    tree(180, False, 0.8).convert("RGB").save(icons / "apple-touch-icon.png")  # iPhones round the corners themselves
    tree(32, True, 0.9).save(ROOT / "web" / "static" / "icon-32.png")


if __name__ == "__main__":
    main()
