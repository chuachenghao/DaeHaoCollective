from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import joblib
import pandas as pd
from django.test import TestCase
from django.urls import reverse

from . import recommendations as rec
from . import sizing
from .models import (
    Cart,
    CartItem,
    Category,
    Customer,
    Product,
    ProductVariant,
    Seller,
    Style,
    create_account,
    set_customer_styles,
    set_product_styles,
)


class InputParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))

    def checked(self, name):
        return [field["value"] for field in self.inputs if field.get("name") == name and "checked" in field]


class SizingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_account("sizing_customer", "sizing@example.com", "SizingTest2026!")
        cls.customer = Customer.objects.create(
            account=cls.user, height=Decimal("172"), weight=Decimal("65")
        )
        cls.cart = Cart.objects.create(customer=cls.customer)
        owner = create_account(
            "sizing_seller", "sizing-seller@example.com", "SizingTest2026!", "SELLER"
        )
        cls.seller = Seller.objects.create(
            account=owner,
            store_name="Sizing collection",
            email="sizing-store@example.com",
            approval_status="APPROVED",
        )
        cls.category = Category.objects.create(name="Tops")
        cls.minimal = Style.objects.create(name="Minimal")
        cls.streetwear = Style.objects.create(name="Streetwear")
        set_customer_styles(cls.customer, [cls.minimal])
        cls.product = cls.make_product("Cotton sizing shirt", cls.minimal)
        cls.other_product = cls.make_product("Streetwear sizing shirt", cls.streetwear)
        cls.small = cls.make_variant(cls.product, "S", "Navy", 8, "SIZ-S-NV")
        cls.medium = cls.make_variant(cls.product, "M", "Navy", 4, "SIZ-M-NV")
        cls.medium_sold_out = cls.make_variant(cls.product, "M", "Cream", 0, "SIZ-M-CR")
        cls.make_variant(cls.product, "L", "Cream", 2, "SIZ-L-CR")
        cls.make_variant(cls.other_product, "S", "Navy", 5, "SIZ-OTHER-S")

    @classmethod
    def make_product(cls, name, style):
        product = Product.objects.create(
            seller=cls.seller,
            category=cls.category,
            name=name,
            description="A fictional piece for checking independent size guidance.",
            price=Decimal("65"),
            is_active=True,
            approval_status="APPROVED",
        )
        set_product_styles(product, [style])
        return product

    @staticmethod
    def make_variant(product, size, colour, stock, sku):
        return ProductVariant.objects.create(
            product=product,
            size=size,
            colour=colour,
            stock_quantity=stock,
            sku=sku,
        )

    def test_saved_artifact_predicts_different_sizes_from_measurements(self):
        artifact = joblib.load(sizing.MODEL_PATH)
        self.assertEqual(artifact["schema_version"], rec.SCHEMA_VERSION)
        self.assertEqual(artifact["feature_names"], rec.FEATURE_NAMES)
        self.assertEqual(artifact["size_schema_version"], 1)
        self.assertEqual(artifact["size_feature_names"], ["height_cm", "weight_kg"])
        self.assertEqual(artifact["size_labels"], ["XS", "S", "M", "L", "XL", "XXL"])
        model = artifact["size_model"]
        self.assertTrue(sizing.size_model_readiness()["ready"])
        for height, weight, expected in [(160, 50, "S"), (172, 65, "M"), (185, 85, "L")]:
            with self.subTest(height=height, weight=weight):
                predicted = sizing.predict_size(height, weight)
                self.assertTrue(predicted["ready"])
                self.assertEqual(predicted["size"], expected)
                actual = model.predict(pd.DataFrame([[height, weight]], columns=["height_cm", "weight_kg"]))[0]
                self.assertEqual(predicted["size"], actual)

    def test_missing_nonfinite_invalid_and_outside_range_measurements_fail_safely(self):
        invalid_pairs = [
            (None, 65), (172, None), ("", 65), ("nonnumeric", 65),
            (float("nan"), 65), (172, float("nan")),
            (float("inf"), 65), (172, float("-inf")),
            (Decimal("NaN"), Decimal("65")),
            (139.9, 65), (210.1, 65), (172, 34.9), (172, 160.1),
        ]
        for height, weight in invalid_pairs:
            with self.subTest(height=height, weight=weight):
                guidance = sizing.predict_size(height, weight)
                self.assertFalse(guidance["ready"])
                self.assertEqual(guidance["size"], "")
                self.assertTrue(guidance["message"])
        for height, weight in [(140, 35), (210, 160), ("172.0", Decimal("65.0"))]:
            with self.subTest(boundary=(height, weight)):
                guidance = sizing.predict_size(height, weight)
                self.assertTrue(guidance["ready"])
                self.assertIn(guidance["size"], ["XS", "S", "M", "L", "XL", "XXL"])

    def test_missing_corrupt_or_incompatible_size_head_does_not_disable_style_ranking(self):
        original = joblib.load(sizing.MODEL_PATH)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.joblib"
            corrupt = root / "corrupt.joblib"
            corrupt.write_bytes(b"not a model")
            old_artifact = original.copy()
            old_artifact.pop("size_model")
            old = root / "style-only.joblib"
            joblib.dump(old_artifact, old)
            incompatible_artifact = original.copy()
            incompatible_artifact["size_model"] = original["model"]
            incompatible = root / "incompatible.joblib"
            joblib.dump(incompatible_artifact, incompatible)
            for model_path in [missing, corrupt, old, incompatible]:
                with self.subTest(path=model_path.name):
                    with patch.object(sizing, "MODEL_PATH", model_path):
                        self.assertFalse(sizing.size_model_readiness()["ready"])
                        self.assertFalse(sizing.predict_size(172, 65)["ready"])
                        selection = rec.recommend_products(self.customer)
                    self.assertTrue(selection["personalised"])
                    self.assertFalse(selection["size_guidance"]["ready"])
                    self.assertEqual(len(selection["products"]), 2)
                    self.assertTrue(all(product.model_ranked for product in selection["products"]))

    def test_product_guidance_checks_exact_estimated_size_and_selected_colour_stock(self):
        for colour, availability, available in [
            ("", "in_stock", True), ("Navy", "in_stock", True),
            ("Cream", "sold_out", False), ("Black", "not_sold", False),
        ]:
            with self.subTest(colour=colour):
                guidance = sizing.product_size_guidance(self.product, 172, 65, colour=colour)
                self.assertTrue(guidance["ready"])
                self.assertEqual(guidance["size"], "M")
                self.assertEqual(guidance["availability"], availability)
                self.assertEqual(guidance["available"], available)
        ProductVariant.objects.filter(pk=self.medium.pk).update(stock_quantity=0)
        sold_out = sizing.product_size_guidance(self.product, 172, 65)
        self.assertEqual(sold_out["availability"], "sold_out")
        self.assertFalse(sold_out["available"])
        # The S and L variants still have stock; neither substitutes for estimated M.
        self.assertEqual(sold_out["size"], "M")
        not_sold = sizing.product_size_guidance(self.other_product, 172, 65)
        self.assertEqual(not_sold["availability"], "not_sold")
        self.assertFalse(not_sold["available"])
        self.assertEqual(not_sold["size"], "M")

    def test_non_letter_size_products_and_missing_measurements_have_no_false_fit_claim(self):
        for label in ["One size", "38"]:
            product = self.make_product("Alternative sizing " + label, self.minimal)
            self.make_variant(product, label, "Navy", 4, "SIZ-ALT-" + label.replace(" ", ""))
            guidance = sizing.product_size_guidance(product, 172, 65)
            self.assertFalse(guidance["ready"])
            self.assertEqual(guidance["size"], "")
            self.assertEqual(guidance["availability"], "unknown")
            self.assertFalse(guidance["available"])
        missing = sizing.product_size_guidance(self.product, None, None)
        self.assertFalse(missing["ready"])
        self.assertEqual(missing["availability"], "unknown")

    def test_recommendations_expose_measurement_based_size_separately_from_style(self):
        before = rec.recommend_products(self.customer)
        self.assertEqual(before["size_guidance"]["size"], "M")
        self.assertFalse(before["size_guidance"]["sample_measurements"])
        self.assertTrue(before["personalised"])
        self.customer.height, self.customer.weight = Decimal("185"), Decimal("85")
        after = rec.recommend_products(self.customer)
        self.assertEqual(after["size_guidance"]["size"], "L")
        self.assertEqual({product.pk for product in before["products"]}, {product.pk for product in after["products"]})
        self.assertTrue(all(product.size_guidance["size"] == "L" for product in after["products"]))
        # Stock guidance must not remove pieces or rewrite relevance classes.
        model = rec._load_artifact(rec.MODEL_PATH)
        for product in after["products"]:
            expected = model.predict(pd.DataFrame([
                rec.feature_row(185, 85, ["minimal"], [style.name.lower() for style in product.get_styles()], "tops")
            ], columns=rec.FEATURE_NAMES))[0]
            self.assertEqual(product.recommendation_score, int(expected))
        set_customer_styles(self.customer, [self.streetwear])
        different_style = rec.recommend_products(self.customer)
        self.assertEqual(different_style["size_guidance"]["size"], "L")

    def test_anonymous_preview_labels_size_as_example_and_never_saves_measurements(self):
        response = self.client.get(reverse("for_you"), {"preview_style": "minimal"})
        selection = response.context["selection"]
        self.assertTrue(selection["size_guidance"]["ready"])
        self.assertEqual(selection["size_guidance"]["size"], "M")
        self.assertTrue(selection["size_guidance"]["sample_measurements"])
        self.assertTrue(all(product.size_guidance["sample_measurements"] for product in selection["products"]))
        self.assertContains(response, "Example size")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.height, Decimal("172"))
        self.assertEqual(self.customer.weight, Decimal("65"))
        self.assertEqual(Customer.objects.count(), 1)

    def test_estimate_does_not_auto_choose_size_and_manual_choice_survives_stock_check(self):
        self.client.force_login(self.user)
        url = reverse("product_detail", args=[self.product.pk])
        response = self.client.get(url)
        self.assertEqual(response.context["size_guidance"]["size"], "M")
        self.assertTrue(response.context["sizing_profile_available"])
        self.assertEqual(response.context["selected_size"], "")
        self.assertEqual(InputParser(response.content.decode()).checked("size"), [])
        selected = self.client.get(url, {"size": "S", "colour": "Navy", "quantity": "2"})
        self.assertEqual(selected.context["selected_size"], "S")
        self.assertEqual(selected.context["selected_colour"], "Navy")
        self.assertEqual(selected.context["quantity"], "2")
        self.assertEqual(selected.context["selected_variant"].pk, self.small.pk)
        self.assertEqual(selected.context["size_guidance"]["size"], "M")
        self.assertEqual(InputParser(selected.content.decode()).checked("size"), ["S"])
        self.assertEqual(InputParser(selected.content.decode()).checked("colour"), ["Navy"])
        cream = self.client.get(url, {"size": "S", "colour": "Cream"})
        self.assertEqual(cream.context["size_guidance"]["availability"], "sold_out")
        purchase = self.client.post(reverse("cart_add", args=[self.product.pk]), {"size": "S", "colour": "Navy", "quantity": 1})
        self.assertEqual(purchase.status_code, 302)
        self.assertEqual(self.cart.items.get().variant_id, self.small.pk)

    def test_profile_needs_measurements_only_and_clearing_removes_saved_estimate(self):
        self.client.force_login(self.user)
        set_customer_styles(self.customer, [])
        response = self.client.get(reverse("profile"))
        self.assertTrue(response.context["size_guidance"]["ready"])
        self.assertEqual(response.context["size_guidance"]["size"], "M")
        CartItem.objects.create(cart=self.cart, variant=self.small, quantity=1)
        cleared = self.client.post(reverse("clear_profile"), follow=True)
        self.assertEqual(cleared.status_code, 200)
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.height)
        self.assertIsNone(self.customer.weight)
        self.assertFalse(cleared.context["size_guidance"]["ready"])
        self.assertFalse(rec.recommend_products(self.customer)["size_guidance"]["ready"])
        detail = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertFalse(detail.context["size_guidance"]["ready"])
        self.assertEqual(InputParser(detail.content.decode()).checked("size"), [])
        self.assertEqual(self.cart.items.get().quantity, 1)
        self.small.refresh_from_db()
        self.assertEqual(self.small.stock_quantity, 8)

    def test_invalid_profile_submission_keeps_estimate_based_on_saved_measurements(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile"),
            {"height": "185", "weight": "85", "styles": ["999999"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("styles", response.context["form"].errors)
        self.assertEqual(response.context["form"]["height"].value(), "185")
        self.assertEqual(response.context["size_guidance"]["size"], "M")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.height, Decimal("172"))
        self.assertEqual(self.customer.weight, Decimal("65"))
