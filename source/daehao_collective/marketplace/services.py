from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Address,
    Cart,
    CartItem,
    Order,
    OrderItem,
    ProductVariant,
    SellerOrder,
)


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def cart_for(customer):
    return Cart.objects.get_or_create(customer=customer)[0]


def cart_summary(customer):
    cart = cart_for(customer)
    items = list(
        cart.items.select_related("variant__product__seller__account").order_by("pk")
    )
    grouped = {}
    total = Decimal("0.00")
    units = 0
    valid = bool(items)
    for item in items:
        line_total = item.subtotal()
        total += line_total
        units += item.quantity
        if item.problem():
            valid = False
        seller = item.variant.product.seller
        if seller.pk not in grouped:
            grouped[seller.pk] = {
                "seller": seller,
                "items": [],
                "subtotal": Decimal("0.00"),
            }
        grouped[seller.pk]["items"].append(item)
        grouped[seller.pk]["subtotal"] += line_total
    return {
        "cart": cart,
        "items": items,
        "groups": list(grouped.values()),
        "total": total,
        "units": units,
        "valid": valid,
    }


def review_details(customer, address):
    summary = cart_summary(customer)
    rows = []
    for item in summary["items"]:
        product = item.variant.product
        rows.append(
            [
                item.pk,
                item.variant_id,
                item.quantity,
                str(product.price),
                product.name,
                item.variant.size,
                item.variant.colour,
                item.variant.sku,
                product.seller_id,
                product.seller.store_name,
                str(product.seller.commission_rate),
            ]
        )
    data = {
        "customer": customer.pk,
        "items": rows,
        "address": [
            address.pk,
            address.recipient_name,
            address.phone_number,
            address.address_line,
            address.postal_code,
            address.country,
        ],
    }
    return data


@transaction.atomic
def add_to_cart(customer, variant_id, quantity):
    if not isinstance(quantity, int) or quantity < 1:
        raise ValidationError("Enter a positive whole-number quantity.")
    Cart.objects.filter(customer_id=customer.pk).update(updated_at=F("updated_at"))
    cart = cart_for(customer)
    variant = ProductVariant.objects.select_related("product__seller__account").get(
        pk=variant_id
    )
    if not variant.available():
        raise ValidationError("This size and colour is currently unavailable.")
    item = cart.items.filter(variant=variant).first()
    combined = quantity + (item.quantity if item else 0)
    if combined > variant.stock_quantity:
        raise ValidationError(
            f"Only {variant.stock_quantity} units are available, including any already in your bag."
        )
    if item:
        item.quantity = combined
        item.save(update_fields=["quantity"])
    else:
        CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)


@transaction.atomic
def update_cart_item(customer, item_id, quantity):
    if not isinstance(quantity, int) or quantity < 0:
        raise ValidationError(
            "Enter a positive whole-number quantity, or remove this item."
        )
    Cart.objects.filter(customer_id=customer.pk).update(updated_at=F("updated_at"))
    cart = cart_for(customer)
    item = cart.items.select_related("variant__product__seller__account").get(
        pk=item_id
    )
    if quantity == 0:
        item.delete()
        return
    if (
        quantity < 1
        or not item.variant.available()
        or quantity > item.variant.stock_quantity
    ):
        raise ValidationError(
            "Choose a positive whole-number quantity within the current stock, or remove this item."
        )
    item.quantity = quantity
    item.save(update_fields=["quantity"])


@transaction.atomic
def place_order(customer, address_id, reviewed_details):
    Cart.objects.filter(customer_id=customer.pk).update(updated_at=F("updated_at"))
    cart = cart_for(customer)

    address = Address.objects.filter(pk=address_id, customer=customer).first()
    if not address:
        raise ValidationError(
            "Select one of your saved delivery addresses and review again."
        )
    summary = cart_summary(customer)
    if not summary["valid"]:
        raise ValidationError(
            "Your bag contains unavailable items or changed stock. Review your bag before continuing."
        )
    if review_details(customer, address) != reviewed_details:
        raise ValidationError(
            "Your bag, prices or delivery details changed. Please review the latest purchase details."
        )
    order = Order.objects.create(
        customer=customer,
        address=address,
        total_amount=money(summary["total"]),
        shipping_name=address.recipient_name,
        shipping_address=address.address_line,
        shipping_postal=address.postal_code,
        shipping_phone=address.phone_number,
    )
    for group in summary["groups"]:
        seller = group["seller"]
        portion = SellerOrder.objects.create(
            order=order,
            seller=seller,
            subtotal=money(group["subtotal"]),
            commission_rate_applied=seller.commission_rate,
            commission_amount=money(group["subtotal"] * seller.commission_rate),
        )
        for item in group["items"]:
            variant = item.variant
            changed = ProductVariant.objects.filter(
                pk=variant.pk, stock_quantity__gte=item.quantity
            ).update(stock_quantity=F("stock_quantity") - item.quantity)
            if not changed:
                raise ValidationError(
                    "Stock changed during checkout. Your bag is unchanged; please review it again."
                )
            OrderItem.objects.create(
                seller_order=portion,
                variant=variant,
                quantity=item.quantity,
                unit_price_at_sale=variant.product.price,
                line_subtotal=money(item.subtotal()),
            )
    cart.items.all().delete()
    return order


@transaction.atomic
def adjust_stock(variant_id, delta):
    if not isinstance(delta, int) or delta == 0:
        raise ValidationError("Enter a non-zero whole-number stock adjustment.")
    changed = ProductVariant.objects.filter(
        pk=variant_id, stock_quantity__gte=max(0, -delta)
    ).update(stock_quantity=F("stock_quantity") + delta)
    if not changed:
        raise ValidationError(
            "This adjustment would make stock negative. Refresh the latest quantity."
        )
    return ProductVariant.objects.get(pk=variant_id)


@transaction.atomic
def advance_fulfilment(portion_id, expected_status, target_status):
    Order.objects.filter(
        pk__in=SellerOrder.objects.filter(pk=portion_id).values("order_id")
    ).update(order_status=F("order_status"))
    portion = SellerOrder.objects.select_related("order").get(pk=portion_id)
    order_id = portion.order_id
    if not portion.items.exists() or not portion.has_consistent_items():
        raise ValidationError(
            "This order's item records need staff review. No fulfilment changes were made."
        )
    if (
        portion.order.payment_status != "PAID"
        or portion.order.order_status == "CANCELLED"
    ):
        raise ValidationError("A cancelled or unpaid order cannot be fulfilled.")
    if portion.fulfilment_status == target_status:
        return portion
    transitions = {"PROCESSING": "SHIPPED", "SHIPPED": "DELIVERED"}
    if (
        portion.fulfilment_status != expected_status
        or transitions.get(portion.fulfilment_status) != target_status
    ):
        raise ValidationError(
            "The order status changed, or this transition is not allowed. Refresh and try the next step."
        )
    portion.fulfilment_status = target_status
    if target_status == "SHIPPED":
        portion.shipped_at = timezone.now()
    portion.save(update_fields=["fulfilment_status", "shipped_at"])
    statuses = list(
        portion.order.seller_orders.values_list("fulfilment_status", flat=True)
    )
    parent_status = (
        "COMPLETED" if all(s == "DELIVERED" for s in statuses) else "PARTIAL"
    )
    Order.objects.filter(pk=order_id).update(order_status=parent_status)
    return portion


@transaction.atomic
def cancel_order(order_id):
    Order.objects.filter(pk=order_id).update(order_status=F("order_status"))
    order = Order.objects.get(pk=order_id)
    if order.order_status == "CANCELLED":
        return order
    if not order.can_cancel():
        raise ValidationError(
            "Cancellation is only available while every retailer portion is processing and payment is paid."
        )
    for portion in order.seller_orders.prefetch_related("items"):
        if not portion.has_consistent_items():
            raise ValidationError(
                "This order's item records need staff review. No cancellation changes were made."
            )
        for item in portion.items.all():
            ProductVariant.objects.filter(pk=item.variant_id).update(
                stock_quantity=F("stock_quantity") + item.quantity
            )
        portion.fulfilment_status = "CANCELLED"
        portion.save(update_fields=["fulfilment_status"])
    order.order_status = "CANCELLED"
    order.payment_status = "REFUNDED"
    order.save(update_fields=["order_status", "payment_status"])
    return order
