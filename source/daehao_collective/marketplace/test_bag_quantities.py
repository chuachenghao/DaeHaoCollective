from decimal import Decimal
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse
from django.utils.html import strip_tags

from .models import (
    Cart, CartItem, Category, Customer, Order, Product, ProductVariant, Seller,
    create_account,
)
from .services import update_cart_item


class BagControlsParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.links = []
        self.current_form = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current_form = {"action": attrs.get("action"), "inputs": [], "buttons": []}
            self.forms.append(self.current_form)
        elif tag == "a":
            self.links.append(attrs.get("href"))
        elif self.current_form is not None and tag in ["input", "button"]:
            self.current_form[tag + "s"].append(attrs)

    def handle_endtag(self, tag):
        if tag == "form":
            self.current_form = None


class BagQuantityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_account("bag_customer", "bag@example.com", "BagTest2026!")
        cls.customer = Customer.objects.create(account=cls.user)
        cls.cart = Cart.objects.create(customer=cls.customer)
        owner = create_account("bag_seller", "bag-seller@example.com", "BagTest2026!", "SELLER")
        cls.seller = Seller.objects.create(
            account=owner, store_name="Bag test label", email="bag-store@example.com",
            approval_status="APPROVED",
        )
        cls.product = Product.objects.create(
            seller=cls.seller, category=Category.objects.create(name="Tops"),
            name="Cotton bag shirt", description="A quantity test garment.",
            price=Decimal("65.00"), approval_status="APPROVED", is_active=True,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, size="M", colour="Navy", sku="BAG-M-NV", stock_quantity=7,
        )
        cls.other_colour = ProductVariant.objects.create(
            product=cls.product, size="M", colour="Cream", sku="BAG-M-CR", stock_quantity=54,
        )
        cls.item = CartItem.objects.create(cart=cls.cart, variant=cls.variant, quantity=2)

    def setUp(self):
        self.client.force_login(self.user)

    def controls(self, response, item=None):
        item = item or self.item
        parser = BagControlsParser(response.content.decode())
        action = reverse("cart_update", args=[item.pk])
        form = next(form for form in parser.forms if form["action"] == action)
        quantity = next(field for field in form["inputs"] if field.get("name") == "quantity")
        update = next(button for button in form["buttons"] if button.get("value") == "update")
        remove = next(button for button in form["buttons"] if button.get("value") == "remove")
        return parser, quantity, update, remove

    def update(self, quantity, follow=True):
        return self.client.post(
            reverse("cart_update", args=[self.item.pk]),
            {"action": "update", "quantity": quantity}, follow=follow,
        )

    def test_bag_shows_exact_variant_stock_with_native_number_input(self):
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, 200)
        parser, quantity, update, remove = self.controls(response)
        self.assertEqual(quantity["type"], "number")
        self.assertEqual(quantity["min"], "1")
        self.assertEqual(quantity["step"], "1")
        self.assertEqual(quantity["max"], "7")
        self.assertEqual(quantity["value"], "2")
        self.assertNotIn("disabled", quantity)
        self.assertNotIn("disabled", update)
        self.assertNotIn("disabled", remove)
        self.assertIn("formnovalidate", remove)
        text = " ".join(strip_tags(response.content.decode()).split())
        self.assertIn("7 in stock", text)
        self.assertIn("Max 7", text)
        self.assertNotIn("54 in stock", text)
        self.assertIn(reverse("checkout"), parser.links)

    def test_typed_updates_set_absolute_quantity_and_recalculate_totals_without_reserving_stock(self):
        for quantity in [3, 7]:
            with self.subTest(quantity=quantity):
                response = self.update(str(quantity))
                self.item.refresh_from_db()
                self.variant.refresh_from_db()
                self.assertEqual(self.item.quantity, quantity)
                self.assertEqual(self.variant.stock_quantity, 7)
                self.assertEqual(response.context["units"], quantity)
                self.assertEqual(response.context["total"], Decimal("65.00") * quantity)
                self.assertEqual(response.context["groups"][0]["subtotal"], Decimal("65.00") * quantity)
                self.assertTrue(response.context["valid"])

    def test_actual_stock_above_ten_thousand_is_the_quantity_limit(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock_quantity=12005)
        initial = self.client.get(reverse("cart"))
        self.assertEqual(self.controls(initial)[1]["max"], "12005")
        response = self.update("12005")
        self.item.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.item.quantity, 12005)
        self.assertEqual(self.variant.stock_quantity, 12005)
        self.assertEqual(response.context["total"], Decimal("780325.00"))
        self.assertTrue(response.context["valid"])

    def test_overstock_and_invalid_quantities_preserve_bag_and_inventory(self):
        for value in ["8", "", "not a number", "1.5", "0", "-1"]:
            with self.subTest(value=value):
                response = self.update(value)
                self.item.refresh_from_db()
                self.variant.refresh_from_db()
                self.assertEqual(self.item.quantity, 2)
                self.assertEqual(self.variant.stock_quantity, 7)
                self.assertEqual(response.context["total"], Decimal("130.00"))
                self.assertTrue(any(message.level_tag == "error" for message in response.context["messages"]))
                if value == "8":
                    self.assertContains(response, "Only 7 units are available")

    def test_stock_change_after_view_is_rechecked_by_the_server(self):
        before = self.client.get(reverse("cart"))
        self.assertEqual(self.controls(before)[1]["max"], "7")
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock_quantity=3)
        response = self.update("6")
        self.item.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertContains(response, "Only 3 units are available")
        self.assertEqual(self.item.quantity, 2)
        self.assertEqual(self.variant.stock_quantity, 3)
        self.assertEqual(self.controls(response)[1]["max"], "3")

    def test_quantity_above_reduced_positive_stock_stays_editable(self):
        CartItem.objects.filter(pk=self.item.pk).update(quantity=5)
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock_quantity=3)
        response = self.client.get(reverse("cart"))
        parser, quantity, update, remove = self.controls(response)
        self.assertEqual(quantity["value"], "5")
        self.assertEqual(quantity["max"], "3")
        self.assertNotIn("disabled", quantity)
        self.assertNotIn("disabled", update)
        self.assertNotIn("disabled", remove)
        self.assertFalse(response.context["valid"])
        self.assertNotIn(reverse("checkout"), parser.links)
        fixed = self.update("3")
        self.item.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)
        self.assertEqual(self.variant.stock_quantity, 3)
        self.assertTrue(fixed.context["valid"])

    def test_unavailable_variants_disable_updates_but_allow_removal_and_block_checkout(self):
        for state in ["sold_out", "suspended"]:
            with self.subTest(state=state):
                Seller.objects.filter(pk=self.seller.pk).update(approval_status="APPROVED")
                stock = 0 if state == "sold_out" else 7
                ProductVariant.objects.filter(pk=self.variant.pk).update(stock_quantity=stock)
                if state == "suspended":
                    Seller.objects.filter(pk=self.seller.pk).update(approval_status="SUSPENDED")
                self.item, _ = CartItem.objects.get_or_create(
                    cart=self.cart, variant=self.variant, defaults={"quantity": 2},
                )
                response = self.client.get(reverse("cart"))
                parser, quantity, update, remove = self.controls(response)
                self.assertIn("disabled", quantity)
                self.assertIn("disabled", update)
                self.assertNotIn("disabled", remove)
                self.assertIn("formnovalidate", remove)
                self.assertFalse(response.context["valid"])
                self.assertNotIn(reverse("checkout"), parser.links)
                self.assertRedirects(self.client.get(reverse("checkout")), reverse("cart"), fetch_redirect_response=False)
                rejected = self.update("1")
                self.item.refresh_from_db()
                self.variant.refresh_from_db()
                self.assertEqual(self.item.quantity, 2)
                self.assertEqual(self.variant.stock_quantity, stock)
                self.assertContains(rejected, "currently unavailable")
                removed = self.client.post(reverse("cart_update", args=[self.item.pk]), {"action": "remove"})
                self.assertRedirects(removed, reverse("cart"), fetch_redirect_response=False)
                self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())
                self.assertFalse(Order.objects.exists())

    def test_customer_cannot_update_or_remove_another_customers_item(self):
        other_user = create_account("other_bag", "other-bag@example.com", "BagTest2026!")
        other_customer = Customer.objects.create(account=other_user)
        other_cart = Cart.objects.create(customer=other_customer)
        other_item = CartItem.objects.create(cart=other_cart, variant=self.variant, quantity=3)
        for data in [{"action": "update", "quantity": "1"}, {"action": "remove"}]:
            response = self.client.post(reverse("cart_update", args=[other_item.pk]), data)
            self.assertEqual(response.status_code, 404)
        with self.assertRaises(CartItem.DoesNotExist):
            update_cart_item(self.customer, other_item.pk, 1)
        self.item.refresh_from_db()
        other_item.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.item.quantity, 2)
        self.assertEqual(other_item.quantity, 3)
        self.assertEqual(self.variant.stock_quantity, 7)
