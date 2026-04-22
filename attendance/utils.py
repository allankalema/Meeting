from io import BytesIO


def build_qr_svg(content: str) -> str:
    import qrcode
    import qrcode.image.svg

    factory = qrcode.image.svg.SvgPathImage
    image = qrcode.make(content, image_factory=factory, box_size=8, border=2)
    stream = BytesIO()
    image.save(stream)
    return stream.getvalue().decode("utf-8")
