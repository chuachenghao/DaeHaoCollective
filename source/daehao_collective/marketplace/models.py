from decimal import Decimal

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models.functions import Lower


class Account(AbstractBaseUser):
    last_login = None
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]
    objects = BaseUserManager()
    accountID = models.BigAutoField(primary_key=True)

    ROLE_CHOICES = [
        ("CUSTOMER", "Customer"),
        ("SELLER", "Seller"),
        ("ADMIN", "Administrator"),
    ]

    username = models.CharField(
        max_length=150, unique=True, validators=[UnicodeUsernameValidator()]
    )
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="CUSTOMER")

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_account_email_lower"),
            models.UniqueConstraint(Lower("username"), name="unique_username_lower"),
        ]


class Admin(models.Model):
    adminID = models.BigAutoField(primary_key=True)
    employee_name = models.CharField(max_length=150)
    account = models.OneToOneField(
        Account,
        on_delete=models.PROTECT,
        related_name="admin_profile",
        db_column="accountID",
    )

    def __str__(self):
        return self.employee_name


class Category(models.Model):
    categoryID = models.BigAutoField(primary_key=True)

    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="unique_category_lower")
        ]

    def __str__(self):
        return self.name


class Style(models.Model):
    styleID = models.BigAutoField(primary_key=True)

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="unique_style_lower")
        ]

    def __str__(self):
        return self.name


class Customer(models.Model):
    customerID = models.BigAutoField(primary_key=True)

    account = models.OneToOneField(
        Account,
        on_delete=models.CASCADE,
        related_name="customer",
        db_column="accountID",
    )
    height = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(140), MaxValueValidator(210)],
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(35), MaxValueValidator(160)],
    )

    def get_styles(self):
        return Style.objects.filter(customerstylepreference__customer=self)

    def __str__(self):
        return self.account.username


class CustomerStylePreference(models.Model):
    preferenceID = models.BigAutoField(primary_key=True)

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, db_column="customerID"
    )
    style = models.ForeignKey(Style, on_delete=models.PROTECT, db_column="styleID")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "style"], name="unique_preference"
            )
        ]


class Seller(models.Model):
    sellerID = models.BigAutoField(primary_key=True)

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("SUSPENDED", "Suspended"),
    ]

    account = models.OneToOneField(
        Account, on_delete=models.PROTECT, related_name="seller", db_column="accountID"
    )
    store_name = models.CharField(max_length=120, unique=True)
    store_description = models.TextField()
    email = models.EmailField()
    approval_status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="PENDING"
    )
    rejection_reason = models.TextField(blank=True)
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.10"),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    reviewed_by = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_sellers",
        db_column="reviewedByAdminID",
    )

    class Meta:
        ordering = ["store_name"]
        constraints = [
            models.UniqueConstraint(Lower("store_name"), name="unique_store_lower")
        ]

    def can_trade(self):
        return self.approval_status == "APPROVED"

    def commission_percent(self):
        return self.commission_rate * 100

    def __str__(self):
        return self.store_name


class Product(models.Model):
    productID = models.BigAutoField(primary_key=True)

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING", "Pending review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("SUSPENDED", "Suspended"),
    ]

    seller = models.ForeignKey(
        Seller, on_delete=models.PROTECT, related_name="products", db_column="sellerID"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        db_column="categoryID",
    )
    name = models.CharField(max_length=160)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    image = models.ImageField(upload_to="products/", blank=True)

    approval_status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="DRAFT"
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_products",
        db_column="reviewedByAdminID",
    )
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="positive_product_price"
            )
        ]

    def get_styles(self):
        return Style.objects.filter(productstyle__product=self)

    def is_purchasable(self):
        return (
            self.is_active
            and self.approval_status == "APPROVED"
            and self.seller.can_trade()
        )

    def in_stock(self):
        for variant in self.variants.all():
            if variant.stock_quantity > 0:
                return True
        return False

    def size_labels(self):
        sizes = []
        for variant in self.variants.all():
            if variant.size not in sizes:
                sizes.append(variant.size)
        return " / ".join(sizes)

    def __str__(self):
        return self.name


class ProductStyle(models.Model):
    productStyleID = models.BigAutoField(primary_key=True)

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column="productID"
    )
    style = models.ForeignKey(Style, on_delete=models.PROTECT, db_column="styleID")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "style"], name="unique_product_style"
            )
        ]


class ProductVariant(models.Model):
    productVariantID = models.BigAutoField(primary_key=True)

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="variants",
        db_column="productID",
    )
    size = models.CharField(max_length=12)
    colour = models.CharField(max_length=40)
    sku = models.CharField(max_length=80, unique=True)
    stock_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "colour"], name="unique_product_variant"
            ),
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0), name="nonnegative_stock"
            ),
        ]

    def clean(self):
        if self.pk and (self.cart_items.exists() or self.order_items.exists()):
            old = ProductVariant.objects.get(pk=self.pk)
            for field in ["product_id", "size", "colour", "sku"]:
                if getattr(self, field) != getattr(old, field):
                    raise ValidationError(
                        "This variant is in a bag or order. Archive it and create a replacement to change its identity."
                    )

    def available(self):
        return self.product.is_purchasable() and self.stock_quantity > 0

    def __str__(self):
        return f"{self.product.name} / {self.colour} / {self.size}"


class Cart(models.Model):
    cartID = models.BigAutoField(primary_key=True)

    customer = models.OneToOneField(
        Customer, on_delete=models.CASCADE, related_name="cart", db_column="customerID"
    )
    updated_at = models.DateTimeField(auto_now=True)


class CartItem(models.Model):
    cartItemID = models.BigAutoField(primary_key=True)

    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", db_column="cartID"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="cart_items",
        db_column="productVariantID",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "variant"], name="unique_cart_variant"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="positive_cart_quantity"
            ),
        ]

    def subtotal(self):
        return self.variant.product.price * self.quantity

    def problem(self):
        if not self.variant.available():
            return "This variant is currently unavailable. Remove it to continue."
        if self.quantity > self.variant.stock_quantity:
            return (
                f"Only {self.variant.stock_quantity} units remain. Update the quantity."
            )
        return ""


class Address(models.Model):
    addressID = models.BigAutoField(primary_key=True)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="addresses",
        db_column="customerID",
    )
    recipient_name = models.CharField(max_length=120)
    phone_number = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(r"^[+\d ()-]{8,20}$", "Enter a valid contact number.")
        ],
    )
    address_line = models.CharField(max_length=250)
    postal_code = models.CharField(
        max_length=6,
        validators=[
            RegexValidator(r"^\d{6}$", "Enter a six-digit Singapore postal code.")
        ],
    )
    country = models.CharField(max_length=30, default="Singapore", editable=False)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return (
            f"{self.recipient_name} — {self.address_line}, Singapore {self.postal_code}"
        )


class Order(models.Model):
    orderID = models.BigAutoField(primary_key=True)

    STATUS_CHOICES = [
        ("PROCESSING", "Processing"),
        ("PARTIAL", "Partially fulfilled"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    PAYMENT_CHOICES = [
        ("PAID", "Paid (demo)"),
        ("REFUNDED", "Refunded (demo)"),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="orders",
        db_column="customerID",
    )
    address = models.ForeignKey(
        Address, on_delete=models.SET_NULL, null=True, blank=True, db_column="addressID"
    )
    order_date = models.DateTimeField(auto_now_add=True)
    order_status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="PROCESSING"
    )
    payment_status = models.CharField(
        max_length=12, choices=PAYMENT_CHOICES, default="PAID"
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_name = models.CharField(max_length=120)
    shipping_address = models.TextField()
    shipping_postal = models.CharField(max_length=6)
    shipping_phone = models.CharField(max_length=20)

    class Meta:
        ordering = ["-order_date", "-pk"]

    def reference(self):
        return f"W-{self.pk:04d}"

    def can_cancel(self):
        if self.payment_status != "PAID" or not self.seller_orders.exists():
            return False
        for portion in self.seller_orders.all():
            if portion.fulfilment_status != "PROCESSING":
                return False
        return True

    def __str__(self):
        return self.reference()


class SellerOrder(models.Model):
    sellerOrderID = models.BigAutoField(primary_key=True)

    STATUS_CHOICES = [
        ("PROCESSING", "Processing"),
        ("SHIPPED", "Shipped"),
        ("DELIVERED", "Delivered"),
        ("CANCELLED", "Cancelled"),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="seller_orders",
        db_column="orderID",
    )
    seller = models.ForeignKey(
        Seller,
        on_delete=models.PROTECT,
        related_name="seller_orders",
        db_column="sellerID",
    )
    fulfilment_status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="PROCESSING"
    )
    tracking_number = models.CharField(max_length=100, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate_applied = models.DecimalField(max_digits=5, decimal_places=4)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "seller"], name="unique_order_seller"
            )
        ]

    def commission_percent(self):
        return self.commission_rate_applied * 100

    def net_revenue(self):
        return self.subtotal - self.commission_amount

    def recognised_commission(self):
        return (
            self.commission_amount
            if self.fulfilment_status == "DELIVERED"
            and self.order.payment_status == "PAID"
            else Decimal("0.00")
        )

    def has_consistent_items(self):
        return not self.items.exclude(
            variant__product__seller_id=self.seller_id
        ).exists()


class OrderItem(models.Model):
    orderItemID = models.BigAutoField(primary_key=True)

    seller_order = models.ForeignKey(
        SellerOrder,
        on_delete=models.PROTECT,
        related_name="items",
        db_column="sellerOrderID",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="order_items",
        db_column="productVariantID",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def clean(self):
        if (
            self.variant_id
            and self.seller_order_id
            and self.variant.product.seller_id != self.seller_order.seller_id
        ):
            raise ValidationError(
                "An order item must belong to the seller fulfilling this portion."
            )


def active_products(products=None):
    if products is None:
        products = Product.objects.all()
    return products.filter(
        is_active=True,
        approval_status="APPROVED",
        seller__approval_status="APPROVED",
    )


def get_admin_profile(account):
    if account.role != "ADMIN":
        raise ValidationError(
            "Only administrator accounts can review marketplace records."
        )
    profile, created = Admin.objects.get_or_create(
        account=account,
        defaults={"employee_name": account.username},
    )
    return profile


def create_account(username, email, password=None, role="CUSTOMER"):
    account = Account(username=username.strip(), email=email.strip().lower(), role=role)
    account.set_password(password)
    account.full_clean(exclude=["password"])
    account.save()
    return account


@transaction.atomic
def set_customer_styles(customer, styles):
    CustomerStylePreference.objects.filter(customer=customer).delete()
    for style in styles:
        CustomerStylePreference.objects.get_or_create(customer=customer, style=style)


@transaction.atomic
def set_product_styles(product, styles):
    ProductStyle.objects.filter(product=product).delete()
    for style in styles:
        ProductStyle.objects.get_or_create(product=product, style=style)
