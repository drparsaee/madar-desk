"""Generate the app icon; requires Pillow only when regenerating the artwork."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
target = root / "assets" / "madar.ico"
target.parent.mkdir(parents=True, exist_ok=True)

s = 512
im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((18, 18, 494, 494), radius=125, fill="#f5f8ff")
d.ellipse((148, 148, 364, 364), outline="#4d79d6", width=75)
d.ellipse((204, 204, 308, 308), fill="#f5f8ff")
d.ellipse((58, 78, 195, 215), fill="#45bda7", outline="#f5f8ff", width=18)
d.ellipse((100, 120, 153, 173), fill="#f5f8ff")

im.save(target, format="ICO", sizes=[(16, 16), (24, 24), (32, 32),
                                      (48, 48), (64, 64), (128, 128),
                                      (256, 256)])
print(target)
