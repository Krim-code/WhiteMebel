from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile

def compress_image(image, format="WEBP", quality=85):
    img = Image.open(image)
    img_io = BytesIO()

    if img.mode != 'RGB':
        img = img.convert('RGB')

    img.save(img_io, format=format, quality=quality, optimize=True)
    return ContentFile(img_io.getvalue(), name=image.name.split('.')[0] + f'.{format.lower()}')