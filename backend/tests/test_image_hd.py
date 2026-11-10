"""Haute définition commune des images IA (engines.image_hd)."""
import io

from PIL import Image

from engines import image_hd


def _png(w, h):
    im = Image.new("RGB", (w, h), (120, 90, 60))
    for x in range(0, w, 16):
        for y in range(h):
            im.putpixel((x, y), (240, 240, 240))
    b = io.BytesIO(); im.save(b, "PNG")
    return b.getvalue()


def test_upscale_to_4k_jpeg():
    data, mime = image_hd.sharpen(_png(1024, 576), "image/png")
    im = Image.open(io.BytesIO(data))
    assert mime == "image/jpeg" and max(im.size) == 3840 and im.size[1] == 2160


def test_png_and_no_downscale():
    data, mime = image_hd.sharpen(_png(4000, 2000), "image/png", fmt="png")
    assert mime == "image/png" and Image.open(io.BytesIO(data)).size == (4000, 2000)


def test_bad_bytes_kept():
    assert image_hd.sharpen(b"not an image", "image/png") == (b"not an image", "image/png")


def test_prompt_once():
    p = image_hd.hd_prompt(image_hd.hd_prompt("A house."))
    assert p.count("maximum resolution") == 1
