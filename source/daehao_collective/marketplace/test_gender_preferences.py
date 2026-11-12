from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pandas as pd

from django.test import TestCase
from django.urls import reverse
from django.utils.html import strip_tags

from . import recommendations as rec
from .forms import ProfileForm
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


class GenderPreferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_account(
            "gender_customer", "gender@example.com", "GenderTest2026!"
        )
        cls.customer = Customer.objects.create(
            account=cls.user, height=Decimal("172"), weight=Decimal("65")
        )
        cls.cart = Cart.objects.create(customer=cls.customer)
        cls.minimal = Style.objects.create(name="Minimal")
        cls.streetwear = Style.objects.create(name="Streetwear")
        set_customer_styles(cls.customer, [cls.minimal])
        owner = create_account(
            "gender_seller", "gender-seller@example.com", "GenderTest2026!", "SELLER"
        )
        cls.seller = Seller.objects.create(
            account=owner,
            store_name="Gender preference collection",
            email="gender-store@example.com",
            approval_status="APPROVED",
        )
        cls.product = Product.objects.create(
            seller=cls.seller,
            category=Category.objects.create(name="Tops"),
            name="Cotton profile shirt",
            description="A fictional shirt for profile preference checks.",
            price=Decimal("65"),
            is_active=True,
            approval_status="APPROVED",
        )
        set_product_styles(cls.product, [cls.minimal])
        cls.variant = ProductVariant.objects.create(
            product=cls.product, size="M", colour="Navy", sku="GENDER-M-NV",
            stock_quantity=8,
        )
        CartItem.objects.create(cart=cls.cart, variant=cls.variant, quantity=2)
        cls.men_product = cls.make_collection_product("MEN", "Men utility shirt", cls.minimal, "GENDER-MEN")
        cls.women_product = cls.make_collection_product("WOMEN", "Women wrap blouse", cls.streetwear, "GENDER-WOMEN")

    @classmethod
    def make_collection_product(cls, collection, name, style, sku):
        product = Product.objects.create(
            seller=cls.seller, category=cls.product.category, collection=collection,
            name=name, description="A fictional collection example.", price=Decimal("70"),
            is_active=True, approval_status="APPROVED",
        )
        set_product_styles(product, [style])
        ProductVariant.objects.create(
            product=product, size="M", colour="Navy", sku=sku, stock_quantity=8,
        )
        return product

    def profile_data(self, gender="", **updates):
        data = {
            "gender": gender, "height": "172", "weight": "65",
            "styles": [str(self.minimal.pk)],
        }
        data.update(updates)
        return data

    def test_gender_choices_are_explicit_optional_and_blank_by_default(self):
        self.assertEqual(self.customer.gender, "")
        field = ProfileForm(instance=self.customer).fields["gender"]
        self.assertFalse(field.required)
        self.assertEqual(
            dict(field.choices),
            {"": "Prefer not to say", "FEMALE": "Woman", "MALE": "Man", "NON_BINARY": "Non-binary"},
        )
        form = ProfileForm(
            {"height": "", "weight": "", "styles": []}, instance=self.customer
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.gender, "")
        self.assertIsNone(self.customer.height)
        self.assertIsNone(self.customer.weight)

    def test_profile_saves_and_reloads_each_selected_gender(self):
        self.client.force_login(self.user)
        for value, label in [("FEMALE", "Woman"), ("MALE", "Man"), ("NON_BINARY", "Non-binary")]:
            with self.subTest(gender=value):
                response = self.client.post(reverse("profile"), self.profile_data(value))
                self.assertRedirects(response, reverse("for_you"), fetch_redirect_response=False)
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.gender, value)
                self.assertEqual(self.customer.get_gender_display(), label)
                self.assertEqual(self.customer.height, Decimal("172"))
                self.assertEqual(self.customer.weight, Decimal("65"))
                self.assertEqual(list(self.customer.get_styles()), [self.minimal])
                reloaded = self.client.get(reverse("profile"))
                self.assertEqual(reloaded.context["form"]["gender"].value(), value)
                for_you = self.client.get(reverse("for_you"))
                self.assertEqual(for_you.context["selection"]["gender"], value)
                self.assertEqual(for_you.context["selection"]["gender_label"], label)
                self.assertContains(for_you, "Saved gender:")
                self.assertContains(for_you, label)

    def test_declining_gender_clears_only_that_preference(self):
        self.client.force_login(self.user)
        Customer.objects.filter(pk=self.customer.pk).update(gender="FEMALE")
        response = self.client.post(reverse("profile"), self.profile_data(""))
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.gender, "")
        self.assertEqual(self.customer.height, Decimal("172"))
        self.assertEqual(self.customer.weight, Decimal("65"))
        self.assertEqual(list(self.customer.get_styles()), [self.minimal])
        for_you = self.client.get(reverse("for_you"))
        self.assertEqual(for_you.context["selection"]["gender"], "")
        self.assertEqual(for_you.context["selection"]["gender_label"], "Prefer not to say")
        self.assertContains(for_you, "Prefer not to say")
        self.assertNotIn("Saved gender: Woman", " ".join(strip_tags(for_you.content.decode()).split()))
        self.assertEqual(self.cart.items.get().quantity, 2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

    def test_invalid_gender_rejects_entire_submission_without_profile_edits(self):
        self.client.force_login(self.user)
        Customer.objects.filter(pk=self.customer.pk).update(gender="NON_BINARY")
        response = self.client.post(
            reverse("profile"),
            self.profile_data("unsupported", height="185", weight="85", styles=[str(self.streetwear.pk)]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("gender", response.context["form"].errors)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.gender, "NON_BINARY")
        self.assertEqual(self.customer.height, Decimal("172"))
        self.assertEqual(self.customer.weight, Decimal("65"))
        self.assertEqual(list(self.customer.get_styles()), [self.minimal])
        self.assertEqual(self.cart.items.get().quantity, 2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

    def test_clear_profile_requires_confirmation_and_preserves_bag_and_stock(self):
        self.client.force_login(self.user)
        Customer.objects.filter(pk=self.customer.pk).update(gender="FEMALE")
        confirmation = self.client.get(reverse("clear_profile"))
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "gender")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.gender, "FEMALE")
        cleared = self.client.post(reverse("clear_profile"), follow=True)
        self.assertEqual(cleared.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.gender, "")
        self.assertIsNone(self.customer.height)
        self.assertIsNone(self.customer.weight)
        self.assertFalse(self.customer.get_styles().exists())
        self.assertEqual(self.cart.items.get().variant_id, self.variant.pk)
        self.assertEqual(self.cart.items.get().quantity, 2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)
        for_you = self.client.get(reverse("for_you"))
        self.assertEqual(for_you.context["selection"]["gender"], "")
        self.assertEqual(for_you.context["selection"]["gender_label"], "Prefer not to say")
        self.assertContains(for_you, "Prefer not to say")

    def test_gender_is_never_inferred_from_username_or_anonymous_style_preview(self):
        account = create_account(
            "woman_account", "unselected-gender@example.com", "GenderTest2026!"
        )
        customer = Customer.objects.create(account=account, height=172, weight=65)
        set_customer_styles(customer, [self.minimal])
        self.assertEqual(customer.gender, "")
        self.assertEqual(rec.recommend_products(customer)["gender"], "")
        anonymous = rec.recommend_products(None, preview_style="minimal")
        self.assertTrue(anonymous["preview"])
        self.assertEqual(anonymous["gender"], "")
        response = self.client.get(reverse("for_you"), {"preview_style": "minimal"})
        self.assertEqual(response.context["selection"]["gender"], "")
        self.assertNotContains(response, "Saved gender:")

    def test_profile_is_private_and_another_customer_sees_only_own_gender(self):
        Customer.objects.filter(pk=self.customer.pk).update(gender="FEMALE")
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))
        self.assertEqual(self.client.get(reverse("for_you"), {"preview_style": "minimal"}).context["selection"]["gender"], "")
        other_account = create_account(
            "other_gender_customer", "other-gender@example.com", "GenderTest2026!"
        )
        other = Customer.objects.create(account=other_account, gender="MALE", height=172, weight=65)
        set_customer_styles(other, [self.minimal])
        self.client.force_login(other_account)
        profile = self.client.get(reverse("profile"))
        self.assertEqual(profile.context["form"]["gender"].value(), "MALE")
        for_you = self.client.get(reverse("for_you"))
        self.assertEqual(for_you.context["selection"]["gender"], "MALE")
        self.assertEqual(for_you.context["selection"]["gender_label"], "Man")
        self.assertNotIn("Saved gender: Woman", " ".join(strip_tags(for_you.content.decode()).split()))


    def test_saved_gender_tailors_candidate_pool_before_unchanged_model_predictions(self):
        expected = {
            "MALE": {self.product.pk, self.men_product.pk},
            "FEMALE": {self.product.pk, self.women_product.pk},
            "": {self.product.pk, self.men_product.pk, self.women_product.pk},
            "NON_BINARY": {self.product.pk, self.men_product.pk, self.women_product.pk},
        }
        model = rec._load_artifact(rec.MODEL_PATH)
        for gender, expected_ids in expected.items():
            with self.subTest(gender=gender):
                self.customer.gender = gender
                selection = rec.recommend_products(self.customer)
                self.assertTrue(selection["personalised"])
                self.assertEqual(selection["gender"], gender)
                self.assertEqual({product.pk for product in selection["products"]}, expected_ids)
                self.assertEqual(selection["evaluated_count"], len(expected_ids))
                self.assertEqual(selection["collection"], {"MALE": "MEN", "FEMALE": "WOMEN"}.get(gender, "ALL"))
                self.assertFalse(selection["collection_preview"])
                for product in selection["products"]:
                    row = rec.feature_row(
                        172, 65, ["minimal"],
                        [style.name.lower() for style in product.get_styles()], "tops",
                    )
                    predicted = model.predict(pd.DataFrame([row], columns=rec.FEATURE_NAMES))[0]
                    self.assertEqual(product.recommendation_score, int(predicted))
                self.assertEqual(selection["model_pick_count"], sum(product.recommendation_score for product in selection["products"]))

    def test_collection_previews_override_saved_selection_temporarily_and_reset(self):
        self.client.force_login(self.user)
        Customer.objects.filter(pk=self.customer.pk).update(gender="MALE")
        expected = {
            "ALL": {self.product.pk, self.men_product.pk, self.women_product.pk},
            "MEN": {self.product.pk, self.men_product.pk},
            "WOMEN": {self.product.pk, self.women_product.pk},
            "UNISEX": {self.product.pk},
        }
        for collection, expected_ids in expected.items():
            with self.subTest(collection=collection):
                response = self.client.get(reverse("for_you"), {"preview_collection": collection})
                self.assertEqual(response.status_code, 200)
                selection = response.context["selection"]
                self.assertEqual(selection["gender"], "MALE")
                self.assertEqual(selection["gender_label"], "Man")
                self.assertEqual(selection["collection"], collection)
                self.assertTrue(selection["collection_preview"])
                self.assertEqual({product.pk for product in selection["products"]}, expected_ids)
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.gender, "MALE")
                self.assertEqual(self.customer.height, Decimal("172"))
                self.assertEqual(list(self.customer.get_styles()), [self.minimal])
        saved = self.client.get(reverse("for_you"))
        self.assertEqual(saved.context["selection"]["collection"], "MEN")
        self.assertFalse(saved.context["selection"]["collection_preview"])
        anonymous = self.client.__class__().get(reverse("for_you"), {"preview_collection": "WOMEN", "preview_style": "minimal"})
        self.assertEqual(anonymous.context["selection"]["gender"], "")
        self.assertEqual(anonymous.context["selection"]["collection"], "WOMEN")
        self.assertEqual({product.pk for product in anonymous.context["selection"]["products"]}, expected["WOMEN"])
        self.assertNotContains(anonymous, "Saved gender:")

    def test_invalid_or_repeated_collection_preview_recovers_saved_candidate_pool(self):
        self.client.force_login(self.user)
        Customer.objects.filter(pk=self.customer.pk).update(gender="MALE")
        for collection in ["unsupported", ["MEN", "WOMEN"]]:
            with self.subTest(collection=collection):
                response = self.client.get(reverse("for_you"), {"preview_collection": collection})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["filter_errors"])
                selection = response.context["selection"]
                self.assertEqual(selection["collection"], "MEN")
                self.assertFalse(selection["collection_preview"])
                self.assertEqual({product.pk for product in selection["products"]}, {self.product.pk, self.men_product.pk})
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.gender, "MALE")

    def test_collection_preview_survives_sort_pagination_style_links_clear_and_comparison(self):
        self.client.force_login(self.user)
        for number in range(12):
            self.make_collection_product("WOMEN", f"Women comparison shirt {number}", self.streetwear, f"GENDER-PAGE-{number}")
        response = self.client.get(reverse("for_you"), {
            "preview_collection": "WOMEN", "preview_style": "streetwear",
            "sort": "price_asc", "size": "M", "colour": "Navy", "page": "2",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["product_count"], 14)
        self.assertEqual(response.context["sort"], "price_asc")
        query = parse_qs(response.context["query_params"])
        self.assertEqual(query["preview_collection"], ["WOMEN"])
        self.assertEqual(query["preview_style"], ["streetwear"])
        self.assertEqual(query["size"], ["M"])
        self.assertContains(response, 'name="preview_collection" value="WOMEN"')
        self.assertNotIn("page", query)
        clear = parse_qs(urlsplit(response.context["clear_filters_url"]).query)
        self.assertEqual(clear["preview_collection"], ["WOMEN"])
        self.assertEqual(clear["preview_style"], ["streetwear"])
        self.assertNotIn("size", clear)
        for preset in response.context["style_previews"]:
            preset_query = parse_qs(urlsplit(preset["url"]).query)
            self.assertEqual(preset_query["preview_collection"], ["WOMEN"])
            self.assertNotIn("page", preset_query)
        saved_collection = parse_qs(urlsplit(response.context["saved_collection_url"]).query)
        self.assertNotIn("preview_collection", saved_collection)
        self.assertEqual(saved_collection["preview_style"], ["streetwear"])
        saved_style = parse_qs(urlsplit(response.context["saved_style_url"]).query)
        self.assertNotIn("preview_style", saved_style)
        self.assertEqual(saved_style["preview_collection"], ["WOMEN"])
        comparison_url = response.context["catalogue_comparison_url"]
        comparison_query = parse_qs(urlsplit(comparison_url).query)
        self.assertEqual(comparison_query["collection"], ["WOMEN"])
        self.assertEqual(comparison_query["stock"], ["1"])
        self.assertNotIn("preview_style", comparison_query)
        comparison = self.client.get(comparison_url)
        self.assertEqual(comparison.context["product_count"], 14)
        self.assertEqual(
            {product.pk for product in comparison.context["page_obj"].paginator.object_list},
            {product.pk for product in response.context["selection"]["products"]},
        )

    def test_collection_and_selected_variant_stock_are_checked_before_model_ranking(self):
        self.client.force_login(self.user)
        Customer.objects.filter(pk=self.customer.pk).update(gender="FEMALE")
        self.women_product.variants.update(stock_quantity=0)
        ProductVariant.objects.create(
            product=self.women_product, size="S", colour="Navy", sku="GENDER-WOMEN-S", stock_quantity=8,
        )
        response = self.client.get(reverse("for_you"), {"size": "M", "colour": "Navy"})
        self.assertEqual(response.context["product_count"], 1)
        self.assertEqual(response.context["selection"]["evaluated_count"], 1)
        self.assertEqual([product.pk for product in response.context["selection"]["products"]], [self.product.pk])
        comparison = self.client.get(response.context["catalogue_comparison_url"])
        self.assertEqual(comparison.context["product_count"], 1)
        self.assertEqual([product.pk for product in comparison.context["products"]], [self.product.pk])
