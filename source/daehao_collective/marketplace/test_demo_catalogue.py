import io
import tempfile
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils.text import slugify

from .demo_catalogue import ADDITIONAL_PRODUCTS, DEMO_COLLECTIONS
from .management.commands.seed_demo import save_demo_image
from .models import Account, Product, ProductStyle, Style, set_customer_styles
from .services import cart_summary


class DemoCatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.media_directory.cleanup)
        cls.media_settings = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.media_settings.enable()
        cls.addClassCleanup(cls.media_settings.disable)
        call_command("seed_demo", stdout=io.StringIO())

    def test_expanded_catalogue_has_four_distinct_garments_for_each_style(self):
        public = Product.objects.filter(
            is_active=True,
            approval_status="APPROVED",
            seller__approval_status="APPROVED",
        )
        self.assertEqual(public.count(), 42)
        self.assertEqual(Product.objects.filter(approval_status="PENDING").count(), 1)
        self.assertEqual(public.filter(collection="MEN").count(), 10)
        self.assertEqual(public.filter(collection="WOMEN").count(), 12)
        self.assertEqual(public.filter(collection="UNISEX").count(), 20)

        for style in Style.objects.all():
            items = [item for item in ADDITIONAL_PRODUCTS if item[4] == slugify(style.name)]
            self.assertEqual(len(items), 4)
            self.assertEqual({item[3] for item in items}, {"tops", "bottoms", "outerwear", "dresses"})
            for item in items:
                product = public.get(name=item[1])
                self.assertEqual(list(product.get_styles()), [style])
                self.assertEqual(product.variants.count(), 6)
                self.assertTrue(product.variants.filter(stock_quantity__gt=0).exists())
                self.assertIn(item[10], product.description)
                self.assertIn(item[11], product.description)
                self.assertEqual(product.collection, DEMO_COLLECTIONS[item[6]])

    def test_reseeding_preserves_edited_products_uploads_inventory_and_customer(self):
        item = ADDITIONAL_PRODUCTS[0]
        product = Product.objects.get(name=item[1])
        product.name = "Seller edited knit top"
        product.price = Decimal("73.00")
        product.description = "Seller supplied construction and care notes."
        product.image.name = "products/my-own-knit-photo.webp"
        product.collection = "WOMEN"
        product.save()
        variant = product.variants.first()
        variant.stock_quantity = 2
        variant.save()
        ProductStyle.objects.filter(product=product).delete()
        customer = Account.objects.get(username="demo_customer").customer
        selected_style = Style.objects.get(name="Vintage")
        set_customer_styles(customer, [selected_style])
        customer.cart.items.all().delete()

        call_command("seed_demo", stdout=io.StringIO())

        product.refresh_from_db()
        variant.refresh_from_db()
        self.assertEqual(Product.objects.filter(is_active=True).count(), 42)
        self.assertEqual(product.name, "Seller edited knit top")
        self.assertEqual(product.price, Decimal("73.00"))
        self.assertEqual(product.description, "Seller supplied construction and care notes.")
        self.assertEqual(product.image.name, "products/my-own-knit-photo.webp")
        self.assertEqual(product.collection, "WOMEN")
        self.assertEqual(variant.stock_quantity, 2)
        self.assertFalse(product.get_styles().exists())
        self.assertEqual(list(customer.get_styles()), [selected_style])
        self.assertEqual(cart_summary(customer)["units"], 0)

    def test_photo_upgrade_only_replaces_seed_managed_illustrations(self):
        product = Product.objects.get(name=ADDITIONAL_PRODUCTS[0][1])
        product.image.name = "products/demo/knit.svg"
        product.save(update_fields=["image"])
        with tempfile.TemporaryDirectory() as directory:
            image_root = Path(directory) / "marketplace/static/marketplace/images/catalogue"
            image_root.mkdir(parents=True)
            (image_root / "test-knit-photo.webp").write_bytes(b"photo fixture")
            with override_settings(BASE_DIR=Path(directory)):
                self.assertTrue(save_demo_image(product, "knit", "test-knit-photo"))
                self.assertEqual(product.image.name, "products/demo/catalogue/test-knit-photo.webp")
                self.assertTrue(product.image.storage.exists(product.image.name))
                self.assertFalse(save_demo_image(product, "knit", "test-knit-photo"))
                # Reseeding also repairs copied media after moving the project.
                product.image.storage.delete(product.image.name)
                self.assertTrue(save_demo_image(product, "knit", "test-knit-photo"))
                self.assertTrue(product.image.storage.exists(product.image.name))
                product.image.name = "products/seller-upload.webp"
                product.save(update_fields=["image"])
                self.assertFalse(save_demo_image(product, "knit", "test-knit-photo"))
                product.refresh_from_db()
                self.assertEqual(product.image.name, "products/seller-upload.webp")

    def test_collection_upgrade_uses_known_skus_and_preserves_other_records(self):
        menswear = Product.objects.get(name="Linen day shirt")
        menswear.name = "Seller-renamed linen shirt"
        menswear.collection = "UNISEX"
        menswear.save(update_fields=["name", "collection"])
        womenswear = Product.objects.get(name="Column midi dress")
        womenswear.collection = "UNISEX"
        womenswear.save(update_fields=["collection"])
        custom_collection = Product.objects.get(name="Crochet collar polo")
        custom_collection.collection = "WOMEN"
        custom_collection.save(update_fields=["collection"])
        unrelated = Product.objects.create(
            seller=menswear.seller, category=menswear.category,
            name="Unrelated seller upload", description="Seller's own item.",
            price=Decimal("40.00"), collection="UNISEX",
        )
        migration = import_module("marketplace.migrations.0003_product_collection")
        migration.tag_existing_demo_products(apps, SimpleNamespace(connection=connection))
        for product in [menswear, womenswear, custom_collection, unrelated]:
            product.refresh_from_db()
        self.assertEqual(menswear.collection, "MEN")
        self.assertEqual(menswear.name, "Seller-renamed linen shirt")
        self.assertEqual(womenswear.collection, "WOMEN")
        self.assertEqual(custom_collection.collection, "WOMEN")
        self.assertEqual(unrelated.collection, "UNISEX")
