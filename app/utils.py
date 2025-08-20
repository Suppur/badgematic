import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

from PIL import Image, ImageDraw, ImageFont
import qrcode


def _decode_photo(photo_data_b64: str) -> Image.Image:
    # photo_data_b64: "data:image/jpeg;base64,...."
    _, b64 = photo_data_b64.split(",", 1)
    raw = base64.b64decode(b64)
    img = Image.open(BytesIO(raw)).convert("RGB")
    return img


def generate_badge_png(
    formdata: Dict[str, str],
    photo_data_b64: str,
    outdir: str = "app/badge_outputs",
    template_path: Optional[str] = "app/static/img/badge_template.png",
) -> str:
    """
    Returns absolute path to generated badge PNG.
    """
    out_dir = Path(outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Canvas
    W, H = 860, 540  # ~CR80 aspect @ ~150dpi, adjust as you wish
    base = Image.new("RGBA", (W, H), "#F9F9F9")  # White base

    # Optional template overlay
    if template_path and Path(template_path).is_file():
        tpl = Image.open(template_path).convert("RGBA").resize((W, H))
        base.alpha_composite(tpl)

    # Photo
    photo = _decode_photo(photo_data_b64)
    # Crop center to 4:5 then resize
    pw, ph = photo.size
    target_ratio = 4 / 5
    cur_ratio = pw / ph
    if cur_ratio > target_ratio:
        new_w = int(ph * target_ratio)
        x0 = (pw - new_w) // 2
        photo = photo.crop((x0, 0, x0 + new_w, ph))
    else:
        new_h = int(pw / target_ratio)
        y0 = (ph - new_h) // 2
        photo = photo.crop((0, y0, pw, y0 + new_h))
    photo = photo.resize((300, 375))
    base.alpha_composite(photo.convert("RGBA"), dest=(40, 80))

    # QR (VCARD)
    vcard = (
        "BEGIN:VCARD\n"
        "VERSION:3.0\n"
        f"N:{formdata.get('name','')}\n"
        f"TEL:{formdata.get('phone','')}\n"
        f"EMAIL:{formdata.get('email','')}\n"
        "ORG:YourOrg\n"
        f"TITLE:{formdata.get('title','')}\n"
        "END:VCARD"
    )
    qr_img = qrcode.make(vcard).resize((140, 140)).convert("RGBA")
    base.alpha_composite(qr_img, dest=(W - 40 - 140, H - 40 - 140))

    # Text
    draw = ImageDraw.Draw(base)
    try:
        font_big = ImageFont.truetype("arial.ttf", 42)
        font_med = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font_big = ImageFont.load_default()
        font_med = ImageFont.load_default()
        font_small = ImageFont.load_default()

    name = formdata.get("name", "")
    title = formdata.get("title", "")
    emp = formdata.get("employee_number", "")

    draw.text((370, 120), name, fill="#0E2A30", font=font_big)  # Teal Blue
    draw.text((370, 180), title, fill="#020F13", font=font_med)  # Black
    draw.text((370, 220), f"#{emp}", fill="#020F13", font=font_small)

    # Save
    fname = f"{emp or 'badge'}_badge.png"
    out_path = out_dir / fname
    base.convert("RGB").save(out_path, "PNG")
    return str(out_path.resolve())