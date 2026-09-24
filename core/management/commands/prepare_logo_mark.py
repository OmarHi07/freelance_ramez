"""Create the header logo mark from the owner's original logo, non-destructively.

The original file is only read, never modified. Example:

    python manage.py prepare_logo_mark design/reference/rawnaq-logo-original.png --preview
    python manage.py prepare_logo_mark design/reference/rawnaq-logo-original.png --box 40,20,520,500

``--preview`` writes ``design/reference/logo-crop-preview.png`` with a 50px grid
so you can choose the crop box (left,top,right,bottom in pixels) around the
illustrated face only. The command then writes:

* static/img/brand/logo-mark.png      (320×320, used in the header)
* static/img/brand/favicon.png        (64×64)
* static/img/brand/apple-touch-icon.png (180×180)
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageDraw, ImageOps

BRAND_DIR = Path(settings.BASE_DIR) / "static" / "img" / "brand"
PREVIEW = Path(settings.BASE_DIR) / "design" / "reference" / "logo-crop-preview.png"


class Command(BaseCommand):
    help = "Make a cropped header mark (and icons) from the original logo without changing the original."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to the original logo image (PNG/JPEG/WebP).")
        parser.add_argument("--box", help="Crop box as left,top,right,bottom in pixels (the face mark only).")
        parser.add_argument("--preview", action="store_true", help="Write a grid preview to choose the crop box.")
        parser.add_argument("--padding", type=float, default=0.08, help="White padding around the mark (0-0.4).")

    def handle(self, *args, **options):
        source = Path(options["source"]).resolve()
        if not source.exists():
            raise CommandError(f"Logo not found: {source}")
        with Image.open(source) as original:
            original.load()
            image = ImageOps.exif_transpose(original).convert("RGBA")
        self.stdout.write(f"Original size: {image.width}×{image.height}px (file is left unchanged).")

        if options["preview"]:
            self._write_preview(image)
            if not options["box"]:
                return

        if not options["box"]:
            raise CommandError("Pass --box left,top,right,bottom (use --preview first to pick the values).")
        try:
            left, top, right, bottom = (int(value) for value in options["box"].split(","))
        except ValueError as exc:
            raise CommandError("--box must be four integers: left,top,right,bottom") from exc
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise CommandError("The crop box is outside the image.")

        mark = image.crop((left, top, right, bottom))
        padding = min(max(options["padding"], 0.0), 0.4)
        side = int(max(mark.size) * (1 + 2 * padding))
        canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
        canvas.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2), mark)

        BRAND_DIR.mkdir(parents=True, exist_ok=True)
        outputs = {"logo-mark.png": 320, "favicon.png": 64}
        for name, size in outputs.items():
            path = BRAND_DIR / name
            if path.resolve() == source:
                raise CommandError("Refusing to overwrite the original logo.")
            canvas.resize((size, size), Image.Resampling.LANCZOS).save(path, optimize=True)
            self.stdout.write(self.style.SUCCESS(f"Wrote {path.relative_to(settings.BASE_DIR)}"))
        touch = Image.new("RGB", (180, 180), (248, 200, 220))
        inner = canvas.resize((150, 150), Image.Resampling.LANCZOS)
        touch.paste(inner, (15, 15), inner)
        touch.save(BRAND_DIR / "apple-touch-icon.png", optimize=True)
        self.stdout.write(self.style.SUCCESS("Wrote static/img/brand/apple-touch-icon.png"))
        self.stdout.write("Run collectstatic again before deploying.")

    def _write_preview(self, image: Image.Image) -> None:
        preview = image.convert("RGB")
        draw = ImageDraw.Draw(preview)
        for x in range(0, preview.width, 50):
            draw.line((x, 0, x, preview.height), fill=(229, 154, 184), width=1)
            draw.text((x + 2, 2), str(x), fill=(158, 82, 111))
        for y in range(0, preview.height, 50):
            draw.line((0, y, preview.width, y), fill=(229, 154, 184), width=1)
            draw.text((2, y + 2), str(y), fill=(158, 82, 111))
        PREVIEW.parent.mkdir(parents=True, exist_ok=True)
        preview.save(PREVIEW)
        self.stdout.write(
            self.style.SUCCESS(f"Preview with 50px grid written to {PREVIEW.relative_to(settings.BASE_DIR)}")
        )
