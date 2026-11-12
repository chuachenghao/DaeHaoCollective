import base64
import io
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import joblib
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import models
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.text import slugify

from . import recommendations as rec
from .forms import (
    ProfileForm,
    RegistrationForm,
    SellerRegistrationForm,
    StaffSellerForm,
    VariantForm,
)
from .models import (
    active_products,
    Account,
    Admin,
    Address,
    Cart,
    CartItem,
    Category,
    Customer,
    CustomerStylePreference,
    Order,
    OrderItem,
    Product,
    ProductStyle,
    ProductVariant,
    SellerOrder,
    Seller,
    Style,
    create_account,
    get_admin_profile,
    set_customer_styles,
    set_product_styles,
)
from .recommendations import model_readiness, recommend_products
from .services import (
    add_to_cart,
    adjust_stock,
    advance_fulfilment,
    cancel_order,
    cart_summary,
    place_order,
    review_details,
)


class MarketplaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=io.StringIO())

    def setUp(self):
        self.user = Account.objects.get(username="demo_customer")
        self.customer = self.user.customer
        self.address = self.customer.addresses.first()
        self.variant = self.customer.cart.items.first().variant
        self.seller = self.variant.product.seller

    def place(self):
        return place_order(
            self.customer,
            self.address.pk,
            review_details(self.customer, self.address),
        )

    def login(self, username="demo_customer"):
        self.client.force_login(Account.objects.get(username=username))

    def test_seed_has_exact_worked_bag_and_is_repeatable(self):
        self.assertEqual(cart_summary(self.customer)["total"], Decimal("220.00"))
        self.assertEqual(cart_summary(self.customer)["units"], 3)
        Product.objects.filter(pk=self.variant.product_id).update(price=Decimal("66"))
        self.customer.cart.items.all().delete()
        call_command("seed_demo", stdout=io.StringIO())
        self.assertFalse(self.customer.cart.items.exists())
        self.assertEqual(
            Product.objects.get(pk=self.variant.product_id).price, Decimal("66")
        )

    def test_registration_creates_customer_cart_and_hashed_password(self):
        form = RegistrationForm(
            {
                "username": "new_student",
                "email": "new@example.com",
                "password1": "SomethingNew2026!",
                "password2": "SomethingNew2026!",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.role, "CUSTOMER")
        self.assertTrue(user.check_password("SomethingNew2026!"))
        self.assertIsNotNone(user.customer.cart)

    def test_registration_rejects_case_insensitive_duplicate_email(self):
        form = RegistrationForm(
            {
                "username": "different",
                "email": self.user.email.upper(),
                "password1": "SomethingNew2026!",
                "password2": "SomethingNew2026!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_seller_registration_never_grants_admin_or_customer(self):
        form = SellerRegistrationForm(
            {
                "username": "new_label",
                "email": "label@example.com",
                "password1": "SomethingNew2026!",
                "password2": "SomethingNew2026!",
                "role": "ADMIN",
                "store_name": "A New Label",
                "store_description": "Independent clothing.",
                "contact_email": "store@example.com",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.role, "SELLER")
        self.assertEqual(user.email, "label@example.com")
        self.assertEqual(user.seller.email, "store@example.com")
        self.assertEqual(user.seller.approval_status, "PENDING")
        self.assertFalse(Customer.objects.filter(account=user).exists())

    def test_profile_range_is_validated_but_optional(self):
        invalid = ProfileForm({"height": 250, "weight": 65}, instance=self.customer)
        self.assertFalse(invalid.is_valid())
        self.assertIn("height", invalid.errors)
        self.assertTrue(
            ProfileForm(
                {"height": "", "weight": "", "styles": []}, instance=self.customer
            ).is_valid()
        )

    def test_added_variant_merges_without_reserving_stock(self):
        stock = self.variant.stock_quantity
        before = self.customer.cart.items.get(variant=self.variant).quantity
        add_to_cart(self.customer, self.variant.pk, 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, stock)
        self.assertEqual(
            self.customer.cart.items.filter(variant=self.variant).count(), 1
        )
        self.assertEqual(
            self.customer.cart.items.get(variant=self.variant).quantity, before + 1
        )

    def test_combined_cart_quantity_cannot_exceed_stock(self):
        with self.assertRaises(ValidationError):
            add_to_cart(self.customer, self.variant.pk, self.variant.stock_quantity)
        self.assertEqual(self.customer.cart.items.get(variant=self.variant).quantity, 2)

    def test_successful_checkout_splits_and_snapshots_exact_amounts(self):
        stock = self.variant.stock_quantity
        order = self.place()
        self.assertEqual(order.total_amount, Decimal("220"))
        self.assertEqual(order.seller_orders.count(), 2)
        self.assertEqual(
            sum(p.subtotal for p in order.seller_orders.all()), order.total_amount
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, stock - 2)
        self.assertFalse(self.customer.cart.items.exists())
        north = order.seller_orders.get(seller=self.seller)
        self.assertEqual(north.commission_amount, Decimal("13.00"))
        self.assertEqual(north.net_revenue(), Decimal("117.00"))
        self.assertEqual(north.recognised_commission(), Decimal("0.00"))

    def test_empty_cart_prevents_a_second_purchase(self):
        fingerprint = review_details(self.customer, self.address)
        stock = self.variant.stock_quantity
        place_order(self.customer, self.address.pk, fingerprint)
        with self.assertRaises(ValidationError):
            place_order(self.customer, self.address.pk, fingerprint)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, stock - 2)
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 1)

    def test_changed_price_requires_fresh_review_and_keeps_bag_stock(self):
        fingerprint = review_details(self.customer, self.address)
        stock = self.variant.stock_quantity
        Product.objects.filter(pk=self.variant.product_id).update(price=99)
        with self.assertRaises(ValidationError):
            place_order(self.customer, self.address.pk, fingerprint)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, stock)
        self.assertEqual(self.customer.cart.items.count(), 2)
        self.assertFalse(Order.objects.exists())

    def test_changed_address_requires_fresh_review(self):
        fingerprint = review_details(self.customer, self.address)
        self.address.address_line = "20 New Street"
        self.address.save()
        with self.assertRaises(ValidationError):
            place_order(self.customer, self.address.pk, fingerprint)

    def test_insufficient_stock_rolls_back_entire_purchase(self):
        fingerprint = review_details(self.customer, self.address)
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock_quantity=1)
        with self.assertRaises(ValidationError):
            place_order(self.customer, self.address.pk, fingerprint)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(SellerOrder.objects.exists())
        self.assertEqual(self.customer.cart.items.count(), 2)

    def test_sale_amounts_and_shipping_survive_live_name_and_address_changes(self):
        order = self.place()
        original = order.seller_orders.get(seller=self.seller)
        Product.objects.filter(pk=self.variant.product_id).update(
            name="Renamed shirt", price=999
        )
        Seller.objects.filter(pk=self.seller.pk).update(
            store_name="Renamed store", commission_rate=Decimal("0.8")
        )
        self.address.delete()
        order.refresh_from_db()
        original.refresh_from_db()
        self.assertIsNone(order.address)
        self.assertEqual(order.shipping_postal, "123456")
        self.assertEqual(original.commission_rate_applied, Decimal("0.1"))
        self.assertEqual(original.commission_amount, Decimal("13"))
        self.assertEqual(original.seller.store_name, "Renamed store")
        item = original.items.select_related("variant__product").get(
            variant=self.variant
        )
        self.assertEqual(item.variant.product.name, "Renamed shirt")
        self.assertEqual(item.unit_price_at_sale, Decimal("65"))
        self.assertEqual(item.line_subtotal, Decimal("130"))
        self.assertEqual(order.total_amount, Decimal("220"))

    def test_cancellation_restores_stock_exactly_once(self):
        stock = self.variant.stock_quantity
        order = self.place()
        cancel_order(order.pk)
        cancel_order(order.pk)
        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.order_status, "CANCELLED")
        self.assertEqual(order.payment_status, "REFUNDED")
        self.assertEqual(self.variant.stock_quantity, stock)
        self.assertTrue(
            all(p.fulfilment_status == "CANCELLED" for p in order.seller_orders.all())
        )

    def test_shipped_portion_blocks_full_cancellation(self):
        order = self.place()
        portion = order.seller_orders.first()
        advance_fulfilment(portion.pk, "PROCESSING", "SHIPPED")
        with self.assertRaises(ValidationError):
            cancel_order(order.pk)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "PARTIAL")
        self.assertEqual(order.payment_status, "PAID")

    def test_fulfilment_requires_each_step_and_parent_completes(self):
        order = self.place()
        for portion in order.seller_orders.all():
            with self.assertRaises(ValidationError):
                advance_fulfilment(portion.pk, "PROCESSING", "DELIVERED")
            advance_fulfilment(portion.pk, "PROCESSING", "SHIPPED")
            advance_fulfilment(portion.pk, "PROCESSING", "SHIPPED")
            advance_fulfilment(portion.pk, "SHIPPED", "DELIVERED")
            portion.refresh_from_db()
            self.assertEqual(portion.recognised_commission(), portion.commission_amount)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "COMPLETED")

    def test_stock_adjustments_apply_deltas_and_reject_negative(self):
        before = self.variant.stock_quantity
        adjust_stock(self.variant.pk, 3)
        adjust_stock(self.variant.pk, -2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, before + 1)
        with self.assertRaises(ValidationError):
            adjust_stock(self.variant.pk, -(before + 2))

    def test_inconsistent_order_items_block_fulfilment(self):
        order = self.place()
        portion = order.seller_orders.get(seller=self.seller)
        other_variant = ProductVariant.objects.exclude(
            product__seller=self.seller
        ).first()
        portion.items.all().update(variant=other_variant)
        self.assertFalse(portion.has_consistent_items())
        with self.assertRaises(ValidationError):
            advance_fulfilment(portion.pk, "PROCESSING", "SHIPPED")
        portion.refresh_from_db()
        self.assertEqual(portion.fulfilment_status, "PROCESSING")

    def test_referenced_variant_identity_is_locked(self):
        form = VariantForm(
            {"size": "XXL", "colour": "Pink", "sku": "HACK"},
            instance=self.variant,
            product=self.variant.product,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertNotEqual(saved.size, "XXL")
        saved.size = "XXL"
        with self.assertRaises(ValidationError):
            saved.full_clean()

    def test_customer_cannot_open_staff_or_seller_pages(self):
        self.login()
        self.assertEqual(
            self.client.get(reverse("operations_dashboard")).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("seller_products")).status_code, 403)

    def test_seller_cannot_edit_another_sellers_product(self):
        self.login("demo_seller")
        other = Product.objects.exclude(seller__account__username="demo_seller").first()
        self.assertEqual(
            self.client.get(
                reverse("seller_product_edit", args=[other.pk])
            ).status_code,
            404,
        )

    def test_signed_in_customer_can_review_checkout_without_activity_field(self):
        self.login()
        self.assertEqual(self.client.get(reverse("checkout")).status_code, 200)
        self.assertNotIn("is_active", {field.name for field in Account._meta.fields})

    def test_suspended_seller_is_hidden_and_existing_bag_blocks_checkout(self):
        Seller.objects.filter(pk=self.seller.pk).update(approval_status="SUSPENDED")
        self.assertNotIn(
            self.variant.product_id, active_products().values_list("pk", flat=True)
        )
        self.assertFalse(cart_summary(self.customer)["valid"])
        with self.assertRaises(ValidationError):
            self.place()

    def test_decline_keeps_cart_stock_and_creates_no_order(self):
        self.login()
        response = self.client.get(reverse("checkout"))
        token = response.context["checkout_token"]
        stock = self.variant.stock_quantity
        response = self.client.post(
            reverse("checkout"), {"checkout_token": token, "action": "decline"}
        )
        self.assertEqual(response.status_code, 302)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, stock)
        self.assertEqual(self.customer.cart.items.count(), 2)
        self.assertFalse(Order.objects.exists())

    def test_http_checkout_replay_works_after_bag_is_empty(self):
        self.login()
        token = self.client.get(reverse("checkout")).context["checkout_token"]
        first = self.client.post(
            reverse("checkout"), {"checkout_token": token, "action": "place"}
        )
        second = self.client.post(
            reverse("checkout"), {"checkout_token": token, "action": "place"}
        )
        self.assertEqual(first.url, second.url)
        self.assertEqual(Order.objects.count(), 1)

    def test_another_customer_cannot_read_order_or_delete_address(self):
        order = self.place()
        stranger = create_account(
            username="stranger",
            email="stranger@example.com",
            password="ExamplePassword1!",
        )
        Customer.objects.create(account=stranger)
        self.client.force_login(stranger)
        self.assertEqual(
            self.client.get(reverse("order_detail", args=[order.pk])).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                reverse("address_delete", args=[self.address.pk])
            ).status_code,
            404,
        )

    def test_post_actions_require_csrf_and_get_never_removes_bag(self):
        secure_client = Client(enforce_csrf_checks=True)
        secure_client.force_login(self.user)
        item = self.customer.cart.items.first()
        self.assertEqual(
            secure_client.post(
                reverse("cart_update", args=[item.pk]), {"action": "remove"}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())

    def test_filter_size_colour_stock_must_match_same_variant(self):
        product = self.variant.product
        product.variants.exclude(pk=self.variant.pk).delete()
        ProductVariant.objects.filter(pk=self.variant.pk).update(
            size="S", colour="Navy"
        )
        ProductVariant.objects.create(
            product=product,
            size="M",
            colour="Cream",
            sku="TEST-CREAM-M",
            stock_quantity=5,
        )
        response = self.client.get(
            reverse("catalogue"),
            {"size": "M", "colour": "Navy", "stock": "1", "q": product.name},
        )
        self.assertNotContains(
            response, f'href="{reverse("product_detail", args=[product.pk])}"'
        )

    def test_invalid_catalogue_price_and_page_are_recoverable(self):
        response = self.client.get(
            reverse("catalogue"), {"min_price": "NaN", "page": "garbage"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid non-negative price")

    def test_real_model_and_fallback_states(self):
        self.assertTrue(model_readiness()["ready"])
        result = recommend_products(self.customer)
        self.assertTrue(result["personalised"])
        self.assertGreater(len(result["products"]), 0)
        self.customer.height = None
        self.customer.save()
        self.assertFalse(recommend_products(self.customer)["personalised"])

    def test_unknown_style_falls_back_without_breaking_shopping(self):
        unknown = Style.objects.create(name="Experimental")
        CustomerStylePreference.objects.create(customer=self.customer, style=unknown)
        result = recommend_products(self.customer)
        self.assertFalse(result["personalised"])
        self.assertGreater(len(result["products"]), 0)
        self.assertEqual(self.client.get(reverse("catalogue")).status_code, 200)

    @override_settings(DEBUG=False)
    def test_helpful_404_has_recovery_link(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, reverse("catalogue"), status_code=404)

    @override_settings(DEBUG=True)
    def test_local_debug_mode_also_uses_helpful_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, reverse("catalogue"), status_code=404)


class ManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = create_account(
            "staff", "staff@test.example", "CourseworkTest2026!", role="ADMIN"
        )
        cls.staff_profile = get_admin_profile(cls.staff)
        cls.seller_user = create_account(
            "seller", "seller@test.example", "CourseworkTest2026!", role="SELLER"
        )
        cls.other_user = create_account(
            "other", "other@test.example", "CourseworkTest2026!", role="SELLER"
        )
        cls.customer_user = create_account(
            "customer", "customer@test.example", "CourseworkTest2026!", role="CUSTOMER"
        )
        cls.customer = Customer.objects.create(account=cls.customer_user)
        cls.seller = Seller.objects.create(
            account=cls.seller_user,
            store_name="First label",
            store_description="Independent clothing",
            email="first@test.example",
            approval_status="APPROVED",
        )
        cls.other_seller = Seller.objects.create(
            account=cls.other_user,
            store_name="Other label",
            store_description="Independent clothing",
            email="other@test.example",
            approval_status="APPROVED",
        )
        cls.category = Category.objects.create(name="Tops")
        cls.style = Style.objects.create(name="Minimal")
        cls.product = Product.objects.create(
            seller=cls.seller,
            category=cls.category,
            name="Linen shirt",
            description="Everyday linen",
            price="65.00",
            approval_status="APPROVED",
            is_active=True,
        )
        ProductStyle.objects.create(product=cls.product, style=cls.style)
        cls.variant = ProductVariant.objects.create(
            product=cls.product,
            size="M",
            colour="Navy",
            sku="FIRST-M-NAVY",
            stock_quantity=8,
        )
        cls.order = Order.objects.create(
            customer=cls.customer,
            total_amount="130.00",
            shipping_name="Demo person",
            shipping_address="10 Example Road",
            shipping_postal="123456",
            shipping_phone="81234567",
        )
        cls.portion = SellerOrder.objects.create(
            order=cls.order,
            seller=cls.seller,
            subtotal="130.00",
            commission_rate_applied="0.10",
            commission_amount="13.00",
        )

    def test_staff_seller_setup_keeps_account_and_store_emails_separate(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("operations_seller_create"),
            {
                "username": "new_label",
                "account_email": "owner@example.com",
                "password": "NewRetailer2026!",
                "store_name": "A New Label",
                "store_description": "Independent everyday clothing.",
                "email": "store@example.com",
                "commission_percent": "10",
            },
        )
        self.assertEqual(response.status_code, 302)
        account = Account.objects.get(username="new_label")
        self.assertEqual(account.role, "SELLER")
        self.assertEqual(account.email, "owner@example.com")
        self.assertEqual(account.seller.email, "store@example.com")
        self.assertEqual(account.seller.approval_status, "PENDING")

    def test_customers_cannot_access_or_post_to_staff_routes(self):
        self.client.force_login(self.customer_user)
        for route in [
            "operations_dashboard",
            "operations_sellers",
            "operations_customers",
            "operations_commissions",
        ]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("operations_inventory_adjust", args=[self.variant.pk]),
                {"delta": 100},
            ).status_code,
            403,
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

    def test_seller_cannot_open_other_sellers_product_variant_or_order(self):
        self.client.force_login(self.other_user)
        for route, pk in [
            ("seller_product_edit", self.product.pk),
            ("seller_variant_edit", self.variant.pk),
            ("seller_inventory_adjust", self.variant.pk),
            ("seller_order_detail", self.portion.pk),
        ]:
            self.assertEqual(
                self.client.get(reverse(route, args=[pk])).status_code, 404
            )
            self.assertEqual(
                self.client.post(
                    reverse(route, args=[pk]),
                    {
                        "delta": 100,
                        "target_status": "SHIPPED",
                        "expected_status": "PROCESSING",
                    },
                ).status_code,
                404,
            )

    def test_pending_or_suspended_sellers_cannot_use_operational_tools(self):
        self.client.force_login(self.seller_user)
        for status in ["PENDING", "SUSPENDED", "REJECTED"]:
            Seller.objects.filter(pk=self.seller.pk).update(approval_status=status)
            response = self.client.post(
                reverse("seller_inventory_adjust", args=[self.variant.pk]), {"delta": 2}
            )
            self.assertRedirects(response, reverse("seller_status"))
            self.assertEqual(self.client.get(reverse("seller_orders")).status_code, 200)
            self.assertEqual(self.client.get(reverse("seller_sales")).status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

    def test_referenced_variant_identity_locked_and_stock_not_overwritten(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        form = VariantForm(
            {
                "size": "XL",
                "colour": "Cream",
                "sku": "FORGED",
                "stock_quantity": 900,
            },
            instance=self.variant,
            product=self.product,
        )
        self.assertTrue(form.is_valid(), form.errors)
        variant = form.save(commit=False)
        variant.save(update_fields=["size", "colour", "sku"])
        variant.refresh_from_db()
        self.assertEqual(
            (variant.size, variant.colour, variant.sku, variant.stock_quantity),
            ("M", "Navy", "FIRST-M-NAVY", 8),
        )

    def test_commission_change_applies_only_to_future_orders(self):
        form = StaffSellerForm(
            {
                "store_name": self.seller.store_name,
                "store_description": self.seller.store_description,
                "email": self.seller.email,
                "commission_percent": "12.50",
            },
            instance=self.seller,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.seller.refresh_from_db()
        self.portion.refresh_from_db()
        self.assertEqual(self.seller.commission_rate, Decimal("0.1250"))
        self.assertEqual(self.portion.commission_rate_applied, Decimal("0.1000"))
        self.assertEqual(self.portion.commission_amount, Decimal("13.00"))

    def test_taxonomy_reference_protection_and_normalised_duplicates(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("operations_categories"),
            {"action": "delete", "record_id": self.category.pk, "confirm": "yes"},
            follow=True,
        )
        self.assertContains(response, "1 products use this category")
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        response = self.client.post(
            reverse("operations_styles"),
            {"name": "  minimal  ", "description": "Duplicate"},
        )
        self.assertContains(response, "This name already exists")
        self.assertEqual(Style.objects.count(), 1)

    def test_negative_inventory_adjustment_rejected_and_delta_applied(self):
        self.client.force_login(self.seller_user)
        response = self.client.post(
            reverse("seller_inventory_adjust", args=[self.variant.pk]), {"delta": -9}
        )
        self.assertContains(response, "make stock negative")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)
        self.client.post(
            reverse("seller_inventory_adjust", args=[self.variant.pk]), {"delta": 3}
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 11)

    def test_rejected_application_needs_reason_and_stale_review_fails(self):
        Seller.objects.filter(pk=self.seller.pk).update(approval_status="PENDING")
        self.client.force_login(self.staff)
        route = reverse("operations_seller_edit", args=[self.seller.pk])
        self.client.post(
            route, {"action": "reject", "confirm": "yes", "expected_status": "PENDING"}
        )
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.approval_status, "PENDING")
        self.client.post(
            route, {"action": "approve", "confirm": "yes", "expected_status": "PENDING"}
        )
        self.client.post(
            route,
            {
                "action": "reject",
                "confirm": "yes",
                "expected_status": "PENDING",
                "reason": "Stale action",
            },
        )
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.approval_status, "APPROVED")

    def test_commission_export_recognises_only_delivered_paid_portions(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("operations_commissions"), {"export": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("130.00,10.0000,13.00,0.00,117.00", response.content.decode())
        SellerOrder.objects.filter(pk=self.portion.pk).update(
            fulfilment_status="DELIVERED"
        )
        response = self.client.get(
            reverse("operations_commissions"), {"export": "csv", "status": "DELIVERED"}
        )
        self.assertIn("130.00,10.0000,13.00,13.00,117.00", response.content.decode())
        Order.objects.filter(pk=self.order.pk).update(payment_status="REFUNDED")
        response = self.client.get(
            reverse("operations_commissions"), {"export": "csv", "status": "DELIVERED"}
        )
        self.assertIn("130.00,10.0000,13.00,0.00,117.00", response.content.decode())

    def test_staff_customer_details_are_read_only(self):
        self.client.force_login(self.staff)
        route = reverse("operations_customer_detail", args=[self.customer_user.pk])
        response = self.client.get(route)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="expected_active"')
        response = self.client.post(
            route, {"confirm": "yes", "expected_active": "yes", "role": "ADMIN"}
        )
        self.assertEqual(response.status_code, 405)
        self.customer_user.refresh_from_db()
        self.assertEqual(self.customer_user.role, "CUSTOMER")

    def test_customer_detail_does_not_expose_admin_accounts(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("operations_customer_detail", args=[self.staff.pk]),
            {"confirm": "yes", "expected_active": "yes"},
        )
        self.assertEqual(response.status_code, 404)

    def test_product_needs_variants_then_staff_approval_before_publication(self):
        product = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="New shirt",
            description="New listing",
            price="40.00",
        )
        ProductStyle.objects.create(product=product, style=self.style)
        self.client.force_login(self.seller_user)
        route = reverse("seller_product_edit", args=[product.pk])
        self.client.post(route, {"action": "submit", "confirm": "yes"})
        product.refresh_from_db()
        self.assertEqual(product.approval_status, "DRAFT")
        ProductVariant.objects.create(
            product=product,
            size="S",
            colour="Cream",
            sku="NEW-S-CREAM",
            stock_quantity=3,
        )
        self.client.post(route, {"action": "submit", "confirm": "yes"})
        product.refresh_from_db()
        self.assertEqual(product.approval_status, "PENDING")
        self.assertFalse(product.is_active)
        self.client.post(route, {"action": "publish", "confirm": "yes"})
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.client.force_login(self.staff)
        self.client.post(
            reverse("operations_product_edit", args=[product.pk]),
            {"action": "approve", "expected_status": "PENDING", "confirm": "yes"},
        )
        product.refresh_from_db()
        self.assertEqual(product.approval_status, "APPROVED")
        self.assertTrue(product.is_active)
        self.client.force_login(self.seller_user)
        self.client.post(route, {"action": "archive", "confirm": "yes"})
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.client.post(route, {"action": "publish", "confirm": "yes"})
        product.refresh_from_db()
        self.assertTrue(product.is_active)

    def test_invalid_replacement_image_preserves_existing_image(self):
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1sAAAAASUVORK5CYII="
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            self.settings(MEDIA_ROOT=directory),
        ):
            self.product.image.save(
                "existing.png",
                SimpleUploadedFile("existing.png", png, content_type="image/png"),
            )
            saved_name = self.product.image.name
            self.client.force_login(self.seller_user)
            response = self.client.post(
                reverse("seller_product_edit", args=[self.product.pk]),
                {
                    "action": "save",
                    "name": self.product.name,
                    "description": self.product.description,
                    "category": self.category.pk,
                    "collection": self.product.collection,
                    "price": "65.00",
                    "styles": [self.style.pk],
                    "image": SimpleUploadedFile(
                        "fake.png", b"this is not an image", content_type="image/png"
                    ),
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors.get("image"))
            self.product.refresh_from_db()
            self.assertEqual(self.product.image.name, saved_name)

    def test_malformed_management_form_ids_return_404(self):
        self.client.force_login(self.staff)
        for invalid in ["abc", "-2", "99999999999999999999999999999"]:
            self.assertEqual(
                self.client.get(
                    reverse("operations_categories"), {"edit": invalid}
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.post(
                    reverse("operations_order_detail", args=[self.order.pk]),
                    {"portion_id": invalid},
                ).status_code,
                404,
            )

    def test_csv_uses_the_same_filtered_rows_and_totals_as_report(self):
        other = SellerOrder.objects.create(
            order=self.order,
            seller=self.other_seller,
            subtotal="90.00",
            commission_rate_applied="0.12",
            commission_amount="10.80",
        )
        self.client.force_login(self.staff)
        filters = {"seller": self.seller.pk, "status": "PROCESSING"}
        report = self.client.get(reverse("operations_commissions"), filters)
        self.assertEqual([p.pk for p in report.context["portions"]], [self.portion.pk])
        self.assertEqual(report.context["totals"]["quoted"], Decimal("13.00"))
        exported = self.client.get(
            reverse("operations_commissions"), {**filters, "export": "csv"}
        ).content.decode()
        self.assertIn("First label", exported)
        self.assertNotIn("Other label", exported)
        self.assertIn("TOTALS,,,,130.00,,13.00,0.00,117.00", exported)


class RecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = create_account(
            username="model_seller", email="model-seller@example.com", role="SELLER"
        )
        cls.seller = Seller.objects.create(
            account=owner,
            store_name="Model Test Store",
            store_description="Fictional fixtures.",
            email=owner.email,
            approval_status="APPROVED",
        )
        cls.user = create_account(
            username="model_customer", email="model-customer@example.com"
        )
        cls.customer = Customer.objects.create(account=cls.user, height=172, weight=65)
        cls.styles = {
            slug: Style.objects.create(name=slug.title()) for slug in rec.STYLE_SLUGS
        }
        cls.categories = {
            slug: Category.objects.create(name=slug.title())
            for slug in rec.CATEGORY_SLUGS
        }
        set_customer_styles(
            cls.customer, [cls.styles["minimal"], cls.styles["workwear"]]
        )
        cls.products = []
        for name, category, tags, price in [
            ("Linen top", "tops", ["minimal", "workwear"], 65),
            ("Evening dress", "dresses", ["formal", "vintage"], 118),
            ("Layer coat", "outerwear", ["minimal", "workwear"], 140),
        ]:
            product = Product.objects.create(
                seller=cls.seller,
                category=cls.categories[category],
                name=name,
                description="A fictional model input fixture.",
                price=price,
                approval_status="APPROVED",
                is_active=True,
            )
            set_product_styles(product, [cls.styles[tag] for tag in tags])
            ProductVariant.objects.create(
                product=product,
                size="M",
                colour="Navy",
                sku=f"MODEL-{product.pk}",
                stock_quantity=10,
            )
            cls.products.append(product)

    def test_missing_artifact_is_not_ready_and_keeps_ordinary_shopping_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(rec, "MODEL_PATH", Path(temporary) / "missing.joblib"):
                self.assertFalse(rec.model_readiness()["ready"])
                result = rec.recommend_products(self.customer)
                self.assertFalse(result["personalised"])
                self.assertEqual(result["reason"], "model_unavailable")
                self.assertEqual(len(result["products"]), 3)
                self.assertEqual(self.client.get(reverse("catalogue")).status_code, 200)

    def test_bad_artifact_schema_and_corrupt_artifact_fail_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "bad.joblib"
            joblib.dump({"schema_version": 999}, artifact)
            with patch.object(rec, "MODEL_PATH", artifact):
                self.assertFalse(rec.model_readiness()["ready"])
            artifact.write_bytes(b"This is not a joblib model.")
            with patch.object(rec, "MODEL_PATH", artifact):
                self.assertFalse(rec.model_readiness()["ready"])
                self.assertEqual(
                    rec.recommend_products(self.customer)["reason"], "model_unavailable"
                )

    def test_missing_corrupt_and_wrong_schema_metadata_fail_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            metadata = Path(temporary) / "metadata.json"
            with patch.object(rec, "METADATA_PATH", metadata):
                self.assertFalse(rec.model_readiness()["ready"])
                metadata.write_text("not json")
                self.assertFalse(rec.model_readiness()["ready"])
                metadata.write_text(json.dumps({"schema_version": 999}))
                self.assertFalse(rec.model_readiness()["ready"])

    def test_artifact_feature_order_and_failed_probe_are_detected(self):
        artifact = joblib.load(rec.MODEL_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "mismatched.joblib"
            artifact["feature_names"] = list(reversed(rec.FEATURE_NAMES))
            joblib.dump(artifact, path)
            with patch.object(rec, "MODEL_PATH", path):
                self.assertFalse(rec.model_readiness()["ready"])
        with patch(
            "sklearn.tree.DecisionTreeClassifier.predict",
            side_effect=ValueError("probe failure"),
        ):
            self.assertFalse(rec.model_readiness()["ready"])

    def test_renamed_style_has_unsupported_taxonomy_fallback(self):
        self.assertTrue(rec.model_readiness()["ready"])
        style = self.styles["minimal"]
        style.name = "Quiet shapes"
        style.save()
        readiness = rec.model_readiness()
        self.assertFalse(readiness["ready"])
        self.assertIn("Quiet shapes", readiness["unsupported_styles"])
        fallback = rec.recommend_products(self.customer)
        self.assertEqual(fallback["reason"], "unsupported_taxonomy")
        self.assertIn("style or category is not supported", fallback["message"])
        self.assertGreater(len(fallback["products"]), 0)

    def test_new_category_has_distinct_fallback_and_preserves_catalogue(self):
        unsupported = Category.objects.create(name="Experimental category")
        Product.objects.filter(pk=self.products[0].pk).update(category=unsupported)
        result = rec.recommend_products(self.customer)
        self.assertFalse(result["personalised"])
        self.assertEqual(result["reason"], "unsupported_taxonomy")
        self.assertIn("style or category is not supported", result["message"])
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(self.client.get(reverse("catalogue")).status_code, 200)

    def test_style_change_changes_real_model_scores_and_rank(self):
        before = rec.recommend_products(self.customer)
        self.assertTrue(before["personalised"])
        self.assertNotEqual(before["products"][0].name, "Evening dress")
        set_customer_styles(
            self.customer, [self.styles["formal"], self.styles["vintage"]]
        )
        after = rec.recommend_products(self.customer)
        self.assertTrue(after["personalised"])
        self.assertEqual(after["products"][0].name, "Evening dress")
        self.assertNotEqual(
            [p.pk for p in before["products"]], [p.pk for p in after["products"]]
        )
        model = joblib.load(rec.MODEL_PATH)["model"]
        product = after["products"][0]
        import pandas as pd

        inputs = pd.DataFrame(
            [
                rec.feature_row(
                    self.customer.height,
                    self.customer.weight,
                    ["formal", "vintage"],
                    [slugify(s.name) for s in product.get_styles()],
                    slugify(product.category.name),
                )
            ],
            columns=rec.FEATURE_NAMES,
        )
        expected = model.predict(inputs)[0]
        self.assertEqual(product.recommendation_score, int(expected))

    def test_measurements_are_used_as_actual_model_inputs(self):
        model = joblib.load(rec.MODEL_PATH)["model"]
        self.assertIn(0, model.tree_.feature)
        self.assertIn(1, model.tree_.feature)
        self.customer.height = Decimal("190")
        self.customer.weight = Decimal("110")
        self.customer.save(update_fields=["height", "weight"])
        with patch.object(rec, "feature_row", wraps=rec.feature_row) as inputs:
            result = rec.recommend_products(self.customer)
        self.assertTrue(result["personalised"])
        self.assertTrue(
            any(
                call.args[0] == Decimal("190") and call.args[1] == Decimal("110")
                for call in inputs.call_args_list
            )
        )
        self.assertTrue(
            all(
                product.recommendation_score in [0, 1] for product in result["products"]
            )
        )

    def test_for_you_all_sorts_preserve_in_stock_variant_filter(self):
        sold_out = self.products[0]
        sold_out.variants.update(stock_quantity=0)

        self.client.force_login(self.user)
        for sort in ["recommended", "name", "price_asc", "price_desc"]:
            with self.subTest(sort=sort):
                response = self.client.get(reverse("for_you"), {"sort": sort})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["selection"]["personalised"])
                self.assertEqual(response.context["product_count"], 2)
                self.assertNotIn(
                    sold_out.pk, [p.pk for p in response.context["products"]]
                )


class UMLModelTests(TestCase):
    def test_uml_models_have_exactly_the_documented_fields_and_explicit_extensions(self):
        expected = {
            Account: "accountID username password email role",
            Admin: "adminID employee_name account",
            Customer: "customerID height weight account",
            Seller: (
                "sellerID store_name store_description email approval_status "
                "rejection_reason commission_rate account reviewed_by"
            ),
            Category: "categoryID name",
            Style: "styleID name description",
            CustomerStylePreference: "preferenceID customer style",
            Product: (
                "productID name description image price approval_status "
                "rejection_reason created_at is_active seller category reviewed_by"
            ),
            ProductStyle: "productStyleID product style",
            ProductVariant: "productVariantID size colour stock_quantity sku product",
            Cart: "cartID updated_at customer",
            CartItem: "cartItemID quantity cart variant",
            Address: (
                "addressID recipient_name phone_number address_line postal_code "
                "country customer"
            ),
            Order: (
                "orderID order_date order_status payment_status total_amount "
                "shipping_name shipping_address shipping_postal shipping_phone "
                "customer address"
            ),
            SellerOrder: (
                "sellerOrderID fulfilment_status tracking_number shipped_at "
                "subtotal commission_rate_applied commission_amount order seller"
            ),
            OrderItem: (
                "orderItemID quantity unit_price_at_sale line_subtotal "
                "seller_order variant"
            ),
        }
        # Gender and garment collection are explicitly requested UML extensions.
        allowed_extensions = {Customer: {"gender"}, Product: {"collection"}}
        for model, fields in expected.items():
            with self.subTest(model=model.__name__):
                actual = {
                    field.name
                    for field in model._meta.get_fields()
                    if field.concrete or (field.many_to_many and not field.auto_created)
                }
                self.assertEqual(actual, set(fields.split()) | allowed_extensions.get(model, set()))

    def test_uml_class_names_and_primary_key_fields(self):
        expected = {
            Account: "accountID",
            Admin: "adminID",
            Customer: "customerID",
            Seller: "sellerID",
            Category: "categoryID",
            Style: "styleID",
            CustomerStylePreference: "preferenceID",
            Product: "productID",
            ProductStyle: "productStyleID",
            ProductVariant: "productVariantID",
            Cart: "cartID",
            CartItem: "cartItemID",
            Address: "addressID",
            Order: "orderID",
            SellerOrder: "sellerOrderID",
            OrderItem: "orderItemID",
        }
        actual = set(apps.get_app_config("marketplace").get_models())
        self.assertEqual(actual, set(expected))
        for model, primary_key in expected.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.pk.name, primary_key)
                self.assertTrue(model._meta.get_field(primary_key).primary_key)
                self.assertEqual(model._meta.pk.column, primary_key)

    def test_uml_domain_attributes_and_field_types(self):
        expected = {
            Account: {
                "username": models.CharField,
                "password": models.CharField,
                "email": models.EmailField,
                "role": models.CharField,
            },
            Admin: {"employee_name": models.CharField},
            Customer: {
                "height": models.DecimalField,
                "weight": models.DecimalField,
                # Explicit profile extension requested after the original UML.
                "gender": models.CharField,
            },
            Seller: {
                "store_name": models.CharField,
                "store_description": models.TextField,
                "email": models.EmailField,
                "approval_status": models.CharField,
                "rejection_reason": models.TextField,
                "commission_rate": models.DecimalField,
            },
            Category: {"name": models.CharField},
            Style: {"name": models.CharField, "description": models.TextField},
            Product: {
                "name": models.CharField,
                "description": models.TextField,
                # Explicit collection tagging extension for gender-aware discovery.
                "collection": models.CharField,
                "image": models.ImageField,
                "price": models.DecimalField,
                "approval_status": models.CharField,
                "rejection_reason": models.TextField,
                "created_at": models.DateTimeField,
                "is_active": models.BooleanField,
            },
            ProductVariant: {
                "size": models.CharField,
                "colour": models.CharField,
                "stock_quantity": models.IntegerField,
                "sku": models.CharField,
            },
            Cart: {"updated_at": models.DateTimeField},
            CartItem: {"quantity": models.IntegerField},
            Address: {
                "recipient_name": models.CharField,
                "phone_number": models.CharField,
                "address_line": models.CharField,
                "postal_code": models.CharField,
                "country": models.CharField,
            },
            Order: {
                "order_date": models.DateTimeField,
                "order_status": models.CharField,
                "payment_status": models.CharField,
                "total_amount": models.DecimalField,
                "shipping_name": models.CharField,
                "shipping_address": models.TextField,
                "shipping_postal": models.CharField,
                "shipping_phone": models.CharField,
            },
            SellerOrder: {
                "fulfilment_status": models.CharField,
                "tracking_number": models.CharField,
                "shipped_at": models.DateTimeField,
                "subtotal": models.DecimalField,
                "commission_rate_applied": models.DecimalField,
                "commission_amount": models.DecimalField,
            },
            OrderItem: {
                "quantity": models.IntegerField,
                "unit_price_at_sale": models.DecimalField,
                "line_subtotal": models.DecimalField,
            },
        }
        for model, fields in expected.items():
            for name, field_type in fields.items():
                with self.subTest(model=model.__name__, field=name):
                    self.assertIsInstance(model._meta.get_field(name), field_type)

    def test_uml_status_shipping_and_relationship_fields(self):
        self.assertIsNotNone(Order._meta.get_field("order_status"))
        self.assertIsNotNone(SellerOrder._meta.get_field("fulfilment_status"))
        self.assertTrue(SellerOrder._meta.get_field("tracking_number").blank)
        self.assertTrue(SellerOrder._meta.get_field("shipped_at").null)
        self.assertIsNotNone(Seller._meta.get_field("email"))
        relationships = [
            (Admin, "account", Account, True, False, "accountID"),
            (Customer, "account", Account, True, False, "accountID"),
            (Seller, "account", Account, True, False, "accountID"),
            (Seller, "reviewed_by", Admin, False, True, "reviewedByAdminID"),
            (Product, "reviewed_by", Admin, False, True, "reviewedByAdminID"),
            (Product, "seller", Seller, False, False, "sellerID"),
            (Product, "category", Category, False, False, "categoryID"),
            (CustomerStylePreference, "customer", Customer, False, False, "customerID"),
            (CustomerStylePreference, "style", Style, False, False, "styleID"),
            (ProductStyle, "product", Product, False, False, "productID"),
            (ProductStyle, "style", Style, False, False, "styleID"),
            (ProductVariant, "product", Product, False, False, "productID"),
            (Cart, "customer", Customer, True, False, "customerID"),
            (CartItem, "cart", Cart, False, False, "cartID"),
            (CartItem, "variant", ProductVariant, False, False, "productVariantID"),
            (Address, "customer", Customer, False, False, "customerID"),
            (Order, "customer", Customer, False, False, "customerID"),
            (Order, "address", Address, False, True, "addressID"),
            (SellerOrder, "order", Order, False, False, "orderID"),
            (SellerOrder, "seller", Seller, False, False, "sellerID"),
            (OrderItem, "seller_order", SellerOrder, False, False, "sellerOrderID"),
            (OrderItem, "variant", ProductVariant, False, False, "productVariantID"),
        ]
        for model, name, target, one_to_one, nullable, column in relationships:
            with self.subTest(model=model.__name__, field=name):
                field = model._meta.get_field(name)
                self.assertEqual(field.remote_field.model, target)
                self.assertEqual(field.one_to_one, one_to_one)
                self.assertEqual(field.null, nullable)
                self.assertEqual(field.column, column)
        self.assertEqual(list(Customer._meta.local_many_to_many), [])
        self.assertEqual(list(Product._meta.local_many_to_many), [])

    def test_uml_unique_keys_and_join_combinations(self):
        unique_fields = [
            (Account, "username"),
            (Account, "email"),
            (Seller, "store_name"),
            (Category, "name"),
            (Style, "name"),
            (ProductVariant, "sku"),
        ]
        for model, name in unique_fields:
            with self.subTest(model=model.__name__, field=name):
                self.assertTrue(model._meta.get_field(name).unique)
        joins = {
            CustomerStylePreference: ("customer", "style"),
            ProductStyle: ("product", "style"),
            ProductVariant: ("product", "size", "colour"),
            CartItem: ("cart", "variant"),
            SellerOrder: ("order", "seller"),
        }
        for model, fields in joins.items():
            with self.subTest(model=model.__name__):
                constraints = [
                    constraint.fields
                    for constraint in model._meta.constraints
                    if isinstance(constraint, models.UniqueConstraint)
                ]
                self.assertIn(fields, constraints)

    def test_admin_profile_is_linked_to_account_and_reused(self):
        account = create_account(
            username="uml_admin",
            email="uml-admin@example.com",
            password="UmlReview2026!",
            role="ADMIN",
        )
        profile = get_admin_profile(account)
        self.assertEqual(profile.account, account)
        self.assertEqual(profile.employee_name, "uml_admin")
        self.assertEqual(get_admin_profile(account).pk, profile.pk)
        self.assertEqual(Admin.objects.filter(account=account).count(), 1)

    def test_staff_setup_command_creates_account_and_admin_together(self):
        with patch(
            "marketplace.management.commands.create_staff.getpass",
            side_effect=["NewEmployee2026!", "NewEmployee2026!"],
        ):
            call_command(
                "create_staff",
                "uml_staff",
                "uml-staff@example.com",
                stdout=io.StringIO(),
            )
        account = Account.objects.get(username="uml_staff")
        self.assertEqual(account.role, "ADMIN")
        self.assertTrue(account.check_password("NewEmployee2026!"))
        self.assertEqual(Admin.objects.get(account=account).employee_name, "uml_staff")
