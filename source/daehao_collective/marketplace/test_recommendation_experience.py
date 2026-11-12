from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
from django.test import TestCase
from django.urls import reverse

from . import recommendations as rec
from .models import (
    Customer,
    Product,
    ProductVariant,
    Seller,
    Style,
    Category,
    create_account,
    set_customer_styles,
    set_product_styles,
)


class RecommendationExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_account("style_customer", "style@example.com", "StyleTest2026!")
        cls.customer = Customer.objects.create(
            account=cls.user, height=Decimal("172"), weight=Decimal("65")
        )
        seller_user = create_account(
            "style_seller", "style-seller@example.com", "StyleTest2026!", "SELLER"
        )
        seller = Seller.objects.create(
            account=seller_user,
            store_name="Style collection",
            email="store@example.com",
            approval_status="APPROVED",
        )
        cls.styles = {slug: Style.objects.create(name=slug.title()) for slug in rec.STYLE_SLUGS}
        categories = {
            slug: Category.objects.create(name=slug.title()) for slug in rec.CATEGORY_SLUGS
        }
        for slug in rec.STYLE_SLUGS:
            for category_slug, category in categories.items():
                product = Product.objects.create(
                    seller=seller,
                    category=category,
                    name=f"{slug.title()} {category_slug}",
                    description="A distinct style example.",
                    price="65.00",
                    is_active=True,
                    approval_status="APPROVED",
                )
                set_product_styles(product, [cls.styles[slug]])
                ProductVariant.objects.create(
                    product=product,
                    size="M",
                    colour="Navy",
                    sku=f"PREVIEW-{slug}-{category_slug}",
                    stock_quantity=10,
                )
        set_customer_styles(cls.customer, [cls.styles["minimal"], cls.styles["workwear"]])

    def test_anonymous_previews_change_actual_model_order_and_explain_example(self):
        minimal = self.client.get(reverse("for_you"), {"preview_style": "minimal"})
        streetwear = self.client.get(reverse("for_you"), {"preview_style": "streetwear"})
        self.assertEqual(minimal.status_code, 200)
        self.assertEqual(streetwear.status_code, 200)
        before, after = minimal.context["selection"], streetwear.context["selection"]
        self.assertTrue(before["personalised"])
        self.assertTrue(after["personalised"])
        self.assertTrue(after["sample_measurements"])
        self.assertNotEqual(
            [product.pk for product in before["products"]],
            [product.pk for product in after["products"]],
        )
        self.assertIn("Minimal", before["products"][0].style_labels)
        self.assertIn("Streetwear", after["products"][0].style_labels)
        self.assertContains(streetwear, "Using an example profile of 172 cm / 65 kg.")
        self.assertContains(streetwear, "Model pick")
        self.assertContains(streetwear, "Compare with all clothing")
        self.assertEqual(after["evaluated_count"], 24)
        self.assertEqual(after["shared_style_count"], 4)
        self.assertEqual(
            after["model_pick_count"],
            sum(p.recommendation_score for p in after["products"]),
        )
        model = rec._load_artifact(rec.MODEL_PATH)
        product = after["products"][0]
        expected = model.predict(
            pd.DataFrame(
                [rec.feature_row(172, 65, ["streetwear"], ["streetwear"], product.category.name.lower())],
                columns=rec.FEATURE_NAMES,
            )
        )[0]
        self.assertEqual(product.recommendation_score, int(expected))

    def test_preview_uses_saved_measurements_without_changing_saved_profile(self):
        self.client.force_login(self.user)
        self.customer.height = Decimal("190")
        self.customer.weight = Decimal("110")
        self.customer.save(update_fields=["height", "weight"])
        original_styles = list(self.customer.get_styles().values_list("pk", flat=True))
        with patch.object(rec, "feature_row", wraps=rec.feature_row) as rows:
            response = self.client.get(reverse("for_you"), {"preview_style": "streetwear"})
        self.assertFalse(response.context["selection"]["sample_measurements"])
        self.assertContains(response, "Using your saved measurements.")
        self.assertTrue(
            any(call.args[:2] == (Decimal("190"), Decimal("110")) for call in rows.call_args_list)
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.height, Decimal("190"))
        self.assertEqual(self.customer.weight, Decimal("110"))
        self.assertEqual(list(self.customer.get_styles().values_list("pk", flat=True)), original_styles)
        saved = self.client.get(reverse("for_you"))
        self.assertFalse(saved.context["selection"]["preview"])
        self.assertEqual(set(saved.context["selection"]["preferred_styles"]), {"Minimal", "Workwear"})

    def test_invalid_or_repeated_preview_style_is_recoverable(self):
        for value in ["unknown", ["minimal", "streetwear"]]:
            response = self.client.get(reverse("for_you"), {"preview_style": value})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Choose a single available style")
            self.assertFalse(response.context["selection"]["preview"])
            self.assertFalse(response.context["selection"]["personalised"])
            self.assertEqual(response.context["sort"], "name")
        self.assertEqual(rec.recommend_products(None, preview_style="unknown")["reason"], "invalid_preview")

    def test_unavailable_model_keeps_preview_honest_and_shopping_available(self):
        with TemporaryDirectory() as directory:
            with patch.object(rec, "MODEL_PATH", Path(directory) / "missing.joblib"):
                response = self.client.get(reverse("for_you"), {"preview_style": "streetwear"})
        selection = response.context["selection"]
        self.assertFalse(selection["personalised"])
        self.assertEqual(selection["reason"], "model_unavailable")
        self.assertEqual(response.context["product_count"], 24)
        self.assertEqual(response.context["sort"], "name")
        self.assertContains(response, "Curated selection")
        self.assertNotContains(response, "Model pick")
        self.assertNotContains(response, "pieces evaluated")
        self.assertFalse(any(p.model_ranked for p in selection["products"]))

    def test_pagination_filter_sort_and_comparison_preserve_correct_context(self):
        response = self.client.get(
            reverse("for_you"),
            {"preview_style": "streetwear", "page": "2", "sort": "price_asc"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["sort"], "price_asc")
        self.assertIn("preview_style=streetwear", response.context["query_params"])
        self.assertNotIn("page=", response.context["query_params"])
        self.assertContains(response, 'name="preview_style" value="streetwear"')
        self.assertIn("preview_style=streetwear", response.context["clear_filters_url"])
        self.assertNotIn("preview_style", response.context["catalogue_comparison_url"])
        self.assertIn("sort=name", response.context["catalogue_comparison_url"])
        for preset in response.context["style_previews"]:
            self.assertNotIn("page=", preset["url"])
            self.assertIn("sort=recommended", preset["url"])
            self.assertTrue(preset["url"].endswith("#clothing-results"))
        self.assertContains(response, 'id="clothing-results"')
        self.assertContains(response, "page=1#clothing-results")
        self.assertContains(response, "Skip filters to clothing")
        self.assertContains(response, "Change style ↑")

    def test_zero_matches_do_not_invent_model_picks(self):
        response = self.client.get(
            reverse("for_you"), {"preview_style": "streetwear", "q": "nonexistent garment"}
        )
        self.assertEqual(response.context["product_count"], 0)
        self.assertFalse(response.context["selection"]["personalised"])
        self.assertNotContains(response, "Model pick")
        self.assertContains(response, "No clothing matches these filters.")

    def test_recommended_variants_and_comparison_respect_selected_size_stock(self):
        product = Product.objects.get(name="Streetwear tops")
        ProductVariant.objects.create(
            product=product,
            size="L",
            colour="Navy",
            sku="PREVIEW-STREETWEAR-L",
            stock_quantity=0,
        )
        response = self.client.get(
            reverse("for_you"), {"preview_style": "streetwear", "size": "L"}
        )
        # Stock in size M must not make the sold-out selected size L recommendable.
        self.assertEqual(response.context["product_count"], 0)
        ordinary = self.client.get(reverse("catalogue"), {"size": "L"})
        self.assertEqual(ordinary.context["product_count"], 1)
        comparison = self.client.get(reverse("catalogue"), {"size": "L", "stock": "1"})
        self.assertEqual(comparison.context["product_count"], 0)
