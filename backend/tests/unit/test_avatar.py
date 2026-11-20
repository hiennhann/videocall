from io import BytesIO
from struct import pack
from zlib import crc32

import pytest
from PIL import Image, PngImagePlugin
from starlette.requests import Request

from app.api.me import read_avatar
from app.core.errors import AuthError, ErrorCode
from app.services.avatar_service import process_avatar


def image_bytes(format: str = "PNG", color: str = "red") -> bytes:
    output = BytesIO()
    with Image.new("RGB", (120, 80), color) as image:
        image.save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_supported_images_become_two_square_webp_files(format: str) -> None:
    key, images = process_avatar(image_bytes(format))
    assert len(key) == 64
    assert key == process_avatar(image_bytes(format))[0]
    for size, data in images.items():
        with Image.open(BytesIO(data)) as image:
            assert image.format == "WEBP"
            assert image.size == (size, size)
            assert not image.getexif()
    assert set(images) == {256, 64}


def test_exif_orientation_is_applied_and_private_metadata_removed() -> None:
    output = BytesIO()
    with Image.new("RGB", (120, 80), "red") as image:
        image.paste("blue", (60, 0, 120, 80))
        exif = Image.Exif()
        exif[274] = 6  # Xoay 90 độ theo chiều kim đồng hồ.
        exif[315] = "private-owner-and-location"
        image.save(output, format="JPEG", exif=exif)
    _, images = process_avatar(output.getvalue())
    with Image.open(BytesIO(images[256])) as image:
        top, bottom = image.getpixel((128, 32)), image.getpixel((128, 224))
        assert top[0] > 200 and top[2] < 30
        assert bottom[2] > 200 and bottom[0] < 30
        assert not image.getexif()
        assert not {"exif", "icc_profile", "xmp"} & image.info.keys()
    assert all(b"private-owner" not in data for data in images.values())


def test_png_text_metadata_is_not_copied() -> None:
    output = BytesIO()
    info = PngImagePlugin.PngInfo()
    info.add_text("GPS", "private-coordinates")
    with Image.new("RGB", (20, 40)) as image:
        image.save(output, format="PNG", pnginfo=info)
    _, images = process_avatar(output.getvalue())
    assert all(b"private-coordinates" not in data for data in images.values())


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>",
        b"not an image",
        image_bytes("GIF"),
        image_bytes("PNG")[:40],
    ],
)
def test_invalid_or_unsupported_content_is_rejected(data: bytes) -> None:
    with pytest.raises(AuthError) as exc:
        process_avatar(data)
    assert exc.value.code == ErrorCode.INVALID_IMAGE


def test_pixel_bomb_is_rejected_before_decoding() -> None:
    data = bytearray(image_bytes())
    data[16:24] = pack(">II", 6000, 5000)
    data[29:33] = pack(">I", crc32(data[12:29]))
    with pytest.raises(AuthError) as exc:
        process_avatar(bytes(data))
    assert exc.value.code == ErrorCode.IMAGE_TOO_LARGE


async def test_multipart_stream_is_stopped_before_reading_unbounded_body() -> None:
    reads = 0

    async def receive():
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"x" * 20000, "more_body": True}

    request = Request(
        {"type": "http", "headers": [(b"content-type", b"multipart/form-data; boundary=test")]},
        receive=receive,
    )
    with pytest.raises(AuthError) as exc:
        await read_avatar(request, 1024)
    assert exc.value.code == ErrorCode.IMAGE_TOO_LARGE
    assert reads == 1
