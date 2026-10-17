# api/management/commands/migrate_product_images.py
from django.core.management.base import BaseCommand
import cloudinary.uploader
from api.models import Product

class Command(BaseCommand):
    help = 'Migrates third-party product image URLs directly to Cloudinary'

    def handle(self, *args, **options):
        products = Product.objects.all()
        total = products.count()
        self.stdout.write(f"Found {total} products to process...")

        success_count = 0
        for product in products:
            # Check where the image source is stored on your Product model
            current_url = getattr(product, 'image_url', None) or getattr(product, 'image', None)
            
            if not current_url:
                continue

            # Convert field object to string if it's an ImageField
            url_str = current_url.url if hasattr(current_url, 'url') else str(current_url)

            # Skip if it's already hosted on Cloudinary or not a valid URL
            if not url_str or 'cloudinary.com' in url_str or not url_str.startswith('http'):
                continue

            try:
                self.stdout.write(f"Uploading image for Product ID {product.id} from {url_str}...")
                
                # Cloudinary uploads the remote URL directly and returns a secure cloud URL
                response = cloudinary.uploader.upload(url_str, folder="products/")
                secure_url = response.get('secure_url')
                
                if secure_url:
                    # Update the database field with the new permanent Cloudinary link
                    if hasattr(product, 'image_url'):
                        product.image_url = secure_url
                    else:
                        product.image = secure_url
                    
                    product.save()
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Migrated -> {secure_url}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed for Product ID {product.id}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Migration complete! Successfully moved {success_count} images to Cloudinary."))