"""Preview concepts at genuine desktop icon sizes. Exploratory only."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "app-icon-comparison.png"
BLUE = "#6094F0"
NAVY = "#0C1A31"
PAPER = "#F5F7FA"

def font(size):
    for name in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()

def get_art(name):
    if name == "Current":
        return Image.open(HERE / "../../public/madar-icon-512.png").convert("RGBA")
    return Image.open(HERE / "render" / f"{name}.png").convert("RGBA")

def tile(art, size, transparent):
    if transparent:
        icon = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(icon)
        d.rounded_rectangle((0, 0, 511, 511), radius=112, fill=NAVY)
        # Symbols occupy the central 76 percent of the icon.
        art = art.resize((424, 424), Image.Resampling.LANCZOS)
        icon.alpha_composite(art, (44, 44))
    else:
        icon = art
    return icon.resize((size, size), Image.Resampling.LANCZOS)

def main():
    labels = [
        ("Current", "Current"),
        ("A / Clear M", "concept-a-monogram"),
        ("B / Orbit", "concept-b-orbit"),
        ("C / Ribbons", "concept-c-ribbons"),
    ]
    img = Image.new("RGB", (1580, 585), PAPER)
    d = ImageDraw.Draw(img)
    d.text((65, 28), "MADAR DESK / ICON CONTEXT", fill="#172B49", font=font(31))
    d.text((65, 73), "Dark navy app tiles   /   preserved brand palette", fill="#586C88", font=font(18))
    for idx, (label, name) in enumerate(labels):
        left = 54 + idx * 385
        d.rounded_rectangle((left, 123, left+355, 547), radius=22, fill="#FFFFFF", outline="#DEE5EF", width=2)
        art = get_art(name)
        icon = tile(art, 230, name != "Current")
        img.paste(icon, (left+62, 149), icon)
        small = tile(art, 32, name != "Current")
        img.paste(small, (left+159, 401), small)
        d.text((left+25, 463), label, fill="#172B49", font=font(24))
        d.text((left+25, 507), "32px view above", fill="#708098", font=font(15))
    img.save(OUT)
    print(OUT)

if __name__ == "__main__":
    main()
