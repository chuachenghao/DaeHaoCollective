from django.test import TestCase
from django.urls import reverse

from .models import Category, Product, ProductStyle, Seller, Style, create_account


class ProductCollectionEditingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = create_account(
            "collection_owner", "owner@example.com", "CollectionTest2026!", "SELLER"
        )
        cls.other_seller = create_account(
            "other_collection_owner", "other@example.com", "CollectionTest2026!", "SELLER"
        )
        cls.staff = create_account(
            "collection_staff", "staff@example.com", "CollectionTest2026!", "ADMIN"
        )
        cls.customer = create_account(
            "collection_customer", "customer@example.com", "CollectionTest2026!"
        )
        for account in [cls.owner, cls.other_seller]:
            Seller.objects.create(
                account=account,
                store_name=account.username,
                email=account.email,
                approval_status="APPROVED",
            )
        cls.category = Category.objects.create(name="Tops")
        cls.style = Style.objects.create(name="Minimal")
        cls.product = Product.objects.create(
            seller=cls.owner.seller,
            category=cls.category,
            name="Cotton shirt",
            description="A cotton shirt with a straight hem.",
            collection="UNISEX",
            price="65.00",
        )
        ProductStyle.objects.create(product=cls.product, style=cls.style)

    def product_data(self, collection):
        return {
            "action": "save",
            "name": self.product.name,
            "description": self.product.description,
            "category": self.category.pk,
            "collection": collection,
            "price": "65.00",
            "styles": [self.style.pk],
        }

    def test_seller_can_change_existing_product_collection(self):
        self.client.force_login(self.owner)
        route = reverse("seller_product_edit", args=[self.product.pk])
        response = self.client.post(route, self.product_data("MEN"))
        self.assertRedirects(response, route, fetch_redirect_response=False)
        self.product.refresh_from_db()
        self.assertEqual(self.product.collection, "MEN")
        self.assertEqual(self.client.get(route).context["form"]["collection"].value(), "MEN")

    def test_staff_can_change_existing_product_collection_without_changing_owner(self):
        self.client.force_login(self.staff)
        route = reverse("operations_product_edit", args=[self.product.pk])
        data = self.product_data("WOMEN")
        data["seller"] = self.other_seller.seller.pk
        response = self.client.post(route, data)
        self.assertRedirects(response, route, fetch_redirect_response=False)
        self.product.refresh_from_db()
        self.assertEqual(self.product.collection, "WOMEN")
        self.assertEqual(self.product.seller_id, self.owner.seller.pk)

    def test_other_seller_and_customer_cannot_change_collection(self):
        self.client.force_login(self.other_seller)
        response = self.client.post(
            reverse("seller_product_edit", args=[self.product.pk]),
            self.product_data("MEN"),
        )
        self.assertEqual(response.status_code, 404)
        self.client.force_login(self.customer)
        for route in ["seller_product_edit", "operations_product_edit"]:
            response = self.client.post(
                reverse(route, args=[self.product.pk]), self.product_data("WOMEN")
            )
            self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertEqual(self.product.collection, "UNISEX")
