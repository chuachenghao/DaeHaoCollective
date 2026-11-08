from decimal import Decimal

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from marketplace.models import (
    Account,
    Admin,
    Address,
    Cart,
    CartItem,
    Category,
    Customer,
    CustomerStylePreference,
    Product,
    ProductStyle,
    ProductVariant,
    Seller,
    Style,
    create_account,
)

DEMO_PASSWORD = "WeftDemo2026!"
STYLE_DATA = [
    ("minimal", "Minimal", "Simple shapes and restrained detail."),
    ("casual", "Casual", "Easy clothing for everyday routines."),
    ("workwear", "Workwear", "Utility-inspired details and layers."),
    ("streetwear", "Streetwear", "Relaxed shapes and graphic details."),
    ("formal", "Formal", "Considered pieces for dressed-up occasions."),
    ("vintage", "Vintage", "Familiar silhouettes with a nostalgic influence."),
]

PRODUCT_DATA = [
    (
        "north",
        "Linen day shirt",
        "65.00",
        "tops",
        ["minimal", "workwear"],
        "shirt",
        "SN-LIN",
        ["Navy", "Cream"],
    ),
    (
        "north",
        "Light layer coat",
        "140.00",
        "outerwear",
        ["workwear", "minimal"],
        "coat",
        "SN-LLC",
        ["Olive", "Navy"],
    ),
    (
        "north",
        "Everyday cotton tee",
        "38.00",
        "tops",
        ["casual", "minimal"],
        "shirt",
        "SN-TEE",
        ["Cream", "Navy"],
    ),
    (
        "north",
        "Utility pocket overshirt",
        "98.00",
        "outerwear",
        ["workwear", "casual"],
        "shirt",
        "SN-OVR",
        ["Olive", "Stone"],
    ),
    (
        "north",
        "Soft rib knit",
        "78.00",
        "tops",
        ["minimal", "casual"],
        "knit",
        "SN-RIB",
        ["Cream", "Navy"],
    ),
    (
        "north",
        "City twill trouser",
        "88.00",
        "bottoms",
        ["workwear", "minimal"],
        "trousers",
        "SN-TWL",
        ["Navy", "Stone"],
    ),
    (
        "form",
        "Easy pleat trouser",
        "90.00",
        "bottoms",
        ["minimal", "workwear"],
        "trousers",
        "FH-EPT",
        ["Stone", "Black"],
    ),
    (
        "form",
        "Boxy poplin shirt",
        "72.00",
        "tops",
        ["minimal", "formal"],
        "shirt",
        "FH-POP",
        ["Cream", "Navy"],
    ),
    (
        "form",
        "Clean line blazer",
        "165.00",
        "outerwear",
        ["formal", "minimal"],
        "coat",
        "FH-BLZ",
        ["Black", "Stone"],
    ),
    (
        "form",
        "Column midi dress",
        "118.00",
        "dresses",
        ["minimal", "formal"],
        "dress",
        "FH-MID",
        ["Black", "Olive"],
    ),
    (
        "still",
        "Relaxed knit cardigan",
        "95.00",
        "tops",
        ["casual", "minimal"],
        "knit",
        "SS-CRD",
        ["Cream", "Stone"],
    ),
    (
        "still",
        "Wide leg denim",
        "105.00",
        "bottoms",
        ["casual", "streetwear"],
        "trousers",
        "SS-DNM",
        ["Navy", "Black"],
    ),
    (
        "still",
        "Studio sweatshirt",
        "68.00",
        "tops",
        ["streetwear", "casual"],
        "knit",
        "SS-SWT",
        ["Stone", "Navy"],
    ),
    (
        "still",
        "Soft jersey dress",
        "76.00",
        "dresses",
        ["casual", "minimal"],
        "dress",
        "SS-JRS",
        ["Olive", "Black"],
    ),
    (
        "sunday",
        "Vintage camp shirt",
        "82.00",
        "tops",
        ["vintage", "casual"],
        "shirt",
        "SA-CMP",
        ["Cream", "Olive"],
    ),
    (
        "sunday",
        "Pleated day skirt",
        "94.00",
        "bottoms",
        ["vintage", "formal"],
        "trousers",
        "SA-SKT",
        ["Stone", "Black"],
    ),
    (
        "sunday",
        "Heritage chore coat",
        "138.00",
        "outerwear",
        ["vintage", "workwear"],
        "coat",
        "SA-CHR",
        ["Olive", "Navy"],
    ),
    (
        "sunday",
        "Evening wrap dress",
        "128.00",
        "dresses",
        ["formal", "vintage"],
        "dress",
        "SA-WRP",
        ["Black", "Cream"],
    ),
]
COLOUR_CODES = {
    "Navy": "NV",
    "Cream": "CR",
    "Olive": "OL",
    "Stone": "ST",
    "Black": "BK",
}


def demo_account(username, email, role):
    existing = Account.objects.filter(email__iexact=email).first()
    if existing is not None:
        return existing
    existing = Account.objects.filter(username=username).first()
    if existing is not None:
        return existing
    return create_account(username, email, DEMO_PASSWORD, role)


def save_demo_image(product, illustration):
    filename = illustration + ".svg"
    source = (
        settings.BASE_DIR
        / "marketplace"
        / "static"
        / "marketplace"
        / "images"
        / filename
    )
    image_name = "products/demo/" + filename
    storage = product.image.storage
    if not storage.exists(image_name):
        with source.open("rb") as image:
            image_name = storage.save(image_name, File(image))
    product.image.name = image_name
    product.save(update_fields=["image"])


class Command(BaseCommand):
    help = "Add fictional DaeHao Collective accounts, 18 public products, one pending listing and a SGD 220 demo bag."

    @transaction.atomic
    def handle(self, *args, **options):
        styles = {}
        for slug, name, description in STYLE_DATA:
            styles[slug], _ = Style.objects.get_or_create(
                name=name, defaults={"description": description}
            )
        categories = {}
        for slug, name in [
            ("tops", "Tops"),
            ("bottoms", "Bottoms"),
            ("outerwear", "Outerwear"),
            ("dresses", "Dresses"),
        ]:
            categories[slug], _ = Category.objects.get_or_create(name=name)

        staff = demo_account("demo_staff", "staff@example.com", "ADMIN")
        staff_profile, _ = Admin.objects.get_or_create(
            account=staff, defaults={"employee_name": "Staff Demo"}
        )
        account = demo_account("demo_customer", "customer@example.com", "CUSTOMER")
        customer, created = Customer.objects.get_or_create(
            account=account,
            defaults={"height": Decimal("172"), "weight": Decimal("65")},
        )
        if created:
            for style in [styles["minimal"], styles["workwear"]]:
                CustomerStylePreference.objects.get_or_create(
                    customer=customer, style=style
                )
            Address.objects.create(
                customer=customer,
                recipient_name="Demo Customer",
                phone_number="+65 8123 4567",
                address_line="10 Example Street, #01-01",
                postal_code="123456",
            )

        seller_data = [
            (
                "north",
                "demo_seller",
                "Studio North",
                "north@example.com",
                "0.10",
                "Considered everyday pieces, with simple shapes and useful details.",
            ),
            (
                "form",
                "demo_form",
                "Form House",
                "form@example.com",
                "0.12",
                "Quiet structure and clean lines for a considered wardrobe.",
            ),
            (
                "still",
                "demo_still",
                "Still Studio",
                "still@example.com",
                "0.10",
                "Comfortable layers and relaxed essentials, made for the everyday.",
            ),
            (
                "sunday",
                "demo_sunday",
                "Sunday Archive",
                "sunday@example.com",
                "0.10",
                "Familiar silhouettes, vintage influences and small everyday discoveries.",
            ),
        ]
        sellers = {}
        for key, username, name, email, rate, description in seller_data:
            owner = demo_account(username, email, "SELLER")
            sellers[key], _ = Seller.objects.get_or_create(
                store_name=name,
                defaults={
                    "account": owner,
                    "store_description": description,
                    "email": email,
                    "approval_status": "APPROVED",
                    "commission_rate": Decimal(rate),
                    "reviewed_by": staff_profile,
                },
            )

        created_products = 0
        products = {}
        for (
            seller_key,
            name,
            price,
            category,
            tags,
            illustration,
            sku_prefix,
            colours,
        ) in PRODUCT_DATA:
            stable_sku = f"{sku_prefix}-{COLOUR_CODES[colours[0]]}-S"
            existing = Product.objects.filter(variants__sku=stable_sku).first()
            if existing is not None:
                products[name] = existing
                continue
            product, is_new = Product.objects.get_or_create(
                seller=sellers[seller_key],
                name=name,
                defaults={
                    "category": categories[category],
                    "price": Decimal(price),
                    "description": (
                        f"{name} from {sellers[seller_key].store_name}. A considered piece for everyday dressing, with an easy silhouette and thoughtful finishing.\n\n"
                        + (
                            "Linen and cotton blend."
                            if name == "Linen day shirt"
                            else "Cotton blend. See the care label on the garment."
                        )
                        + "\n\nGentle cold wash with similar colours. Air dry. Follow the garment care label."
                        + "\n\nS, M and L are retailer size labels. Check the garment measurements with the retailer; recommendations do not guarantee fit."
                    ),
                    "approval_status": "APPROVED",
                    "is_active": True,
                    "reviewed_by": staff_profile,
                },
            )
            products[name] = product
            if not is_new:
                continue
            created_products += 1
            save_demo_image(product, illustration)
            for tag in tags:
                ProductStyle.objects.get_or_create(product=product, style=styles[tag])
            for colour in colours:
                for size in ["S", "M", "L"]:
                    stock = {"S": 8, "M": 12, "L": 6}[size]
                    if name == "Linen day shirt" and size == "M":
                        stock = 3 if colour == "Navy" else 0
                    ProductVariant.objects.create(
                        product=product,
                        size=size,
                        colour=colour,
                        sku=f"{sku_prefix}-{COLOUR_CODES[colour]}-{size}",
                        stock_quantity=stock,
                    )

        pending_owner = demo_account("demo_pending", "atelier@example.com", "SELLER")
        pending_seller, _ = Seller.objects.get_or_create(
            store_name="Atelier New",
            defaults={
                "account": pending_owner,
                "store_description": "A fictional applicant waiting for staff review.",
                "email": "atelier@example.com",
                "approval_status": "PENDING",
            },
        )
        pending_product, pending_created = Product.objects.get_or_create(
            seller=pending_seller,
            name="First collection shirt",
            defaults={
                "category": categories["tops"],
                "price": Decimal("70"),
                "description": "Fictional product waiting for review; never public before approval.",
                "approval_status": "PENDING",
                "is_active": False,
            },
        )
        if pending_created:
            save_demo_image(pending_product, "shirt")
            ProductStyle.objects.get_or_create(
                product=pending_product, style=styles["minimal"]
            )
            ProductVariant.objects.create(
                product=pending_product,
                size="M",
                colour="Cream",
                sku="AN-FST-CR-M",
                stock_quantity=10,
            )

        cart, new_cart = Cart.objects.get_or_create(customer=customer)
        if new_cart:
            shirt = (
                products["Linen day shirt"]
                .variants.filter(size="M", colour="Navy")
                .first()
            )
            trouser = (
                products["Easy pleat trouser"]
                .variants.filter(size="M", colour="Stone")
                .first()
            )
            if shirt and trouser:
                CartItem.objects.create(cart=cart, variant=shirt, quantity=2)
                CartItem.objects.create(cart=cart, variant=trouser, quantity=1)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo ready: added {created_products} public products. Existing records were preserved."
            )
        )
        self.stdout.write(
            "Customer: demo_customer | Seller: demo_seller | Staff: demo_staff"
        )
        self.stdout.write("Demo password for newly created accounts: " + DEMO_PASSWORD)
        self.stdout.write(
            "All brands, addresses and products are fictional. The initial demo bag totals SGD 220.00."
        )
