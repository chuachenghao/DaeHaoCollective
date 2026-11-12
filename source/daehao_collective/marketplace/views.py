import csv
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    login as auth_login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    AccountForm,
    AddressForm,
    InventoryAdjustmentForm,
    ProductForm,
    ProfileForm,
    QuantityForm,
    RegistrationForm,
    ReportFilterForm,
    SellerRegistrationForm,
    StaffProductCreateForm,
    StaffSellerForm,
    StaffSellerCreateForm,
    StoreProfileForm,
    StyleForm,
    TaxonomyForm,
    VariantForm,
    VariantSelectionForm,
)
from .models import (
    Account,
    Address,
    CartItem,
    Category,
    Customer,
    CustomerStylePreference,
    Order,
    Product,
    ProductVariant,
    SellerOrder,
    Seller,
    Style,
    active_products,
    create_account,
    get_admin_profile,
)
from .permissions import check_access
from .services import (
    add_to_cart,
    adjust_stock,
    advance_fulfilment,
    cancel_order,
    cart_summary,
    place_order,
    review_details,
    update_cart_item,
)


def role_home(user):
    if user.role == "ADMIN":
        return "operations_dashboard"
    if user.role == "SELLER":
        return (
            "seller_dashboard"
            if hasattr(user, "seller") and user.seller.can_trade()
            else "seller_status"
        )
    return "home"


def login_view(request, staff=False):
    if request.user.is_authenticated:
        if staff and request.user.role != "ADMIN":
            raise PermissionDenied
        return redirect(role_home(request.user))
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if staff and user.role != "ADMIN":
            form.add_error(None, "This sign-in is for marketplace administrators.")
        else:
            auth_login(request, user)
            next_url = request.POST.get("next", request.GET.get("next", ""))
            if next_url and url_has_allowed_host_and_scheme(
                next_url, {request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect(role_home(user))
    return render(
        request,
        "marketplace/login.html",
        {
            "form": form,
            "staff": staff,
            "next": request.GET.get("next", request.POST.get("next", "")),
        },
    )


def register(request, seller=False):
    if request.user.is_authenticated:
        return redirect(role_home(request.user))
    form_class = SellerRegistrationForm if seller else RegistrationForm
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError:
            form.add_error(
                None,
                "That username, email or store name has just been taken. Please choose another.",
            )
        else:
            auth_login(request, user)
            messages.success(
                request,
                (
                    "Your seller application has been submitted."
                    if seller
                    else f"Welcome to {settings.SITE_NAME}. Your account is ready."
                ),
            )
            return redirect("seller_status" if seller else "home")
    return render(
        request, "marketplace/register.html", {"form": form, "seller": seller}
    )


def logout(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    auth_logout(request)
    messages.success(request, "You have signed out.")
    return redirect("home")


def account(request):
    access = check_access(request, ["CUSTOMER", "SELLER", "ADMIN"])
    if access is not None:
        return access

    form = AccountForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error("email", "This email address is already in use.")
        else:
            messages.success(request, "Account details saved.")
            return redirect("account")
    return render(request, "marketplace/account.html", {"form": form})


def password_change(request):
    access = check_access(request, ["CUSTOMER", "SELLER", "ADMIN"])
    if access is not None:
        return access

    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        messages.success(request, "Your password has been changed.")
        return redirect("account")
    return render(
        request,
        "marketplace/simple_form.html",
        {
            "form": form,
            "title": "Change your password",
            "intro": "Enter your current password and choose a new one.",
            "button_label": "Change password",
            "back_url": reverse("account"),
        },
    )


def profile(request):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    form = ProfileForm(request.POST or None, instance=request.user.customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Your optional personalisation profile has been saved."
        )
        return redirect("for_you")
    from .sizing import predict_size

    customer = Customer.objects.only("height", "weight").get(
        pk=request.user.customer.pk
    )
    return render(
        request,
        "marketplace/profile.html",
        {"form": form, "size_guidance": predict_size(customer.height, customer.weight)},
    )


def clear_profile(request):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    if request.method == "POST":
        with transaction.atomic():
            customer = request.user.customer
            customer.height = None
            customer.weight = None
            customer.gender = ""
            customer.save(update_fields=["height", "weight", "gender"])
            CustomerStylePreference.objects.filter(customer=customer).delete()
        messages.success(
            request,
            "Personalisation information cleared. Your account, bag, addresses and orders are retained.",
        )
        return redirect("profile")
    return render(
        request,
        "marketplace/confirm.html",
        {
            "title": "Clear personalisation?",
            "description": "This removes your saved gender, height, weight and style preferences. Your bag, addresses and orders will remain.",
            "button_label": "Clear personalisation",
            "back_url": reverse("profile"),
        },
    )


def addresses(request):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    return render(
        request,
        "marketplace/addresses.html",
        {"addresses": request.user.customer.addresses.all()},
    )


def address_edit(request, pk=None):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    address = (
        get_object_or_404(Address, pk=pk, customer=request.user.customer)
        if pk
        else None
    )
    form = AddressForm(request.POST or None, instance=address)

    return_checkout = (
        request.GET.get("checkout") == "1" or request.POST.get("checkout") == "1"
    )
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.customer = request.user.customer
        address.save()
        request.session.pop("checkout_review", None)
        messages.success(request, "Delivery address saved.")
        if return_checkout:
            return redirect(
                reverse("checkout") + "?" + urlencode({"address": address.pk})
            )
        return redirect("addresses")
    return render(
        request,
        "marketplace/simple_form.html",
        {
            "form": form,
            "title": "Edit delivery address" if pk else "Add delivery address",
            "intro": "Demo delivery is available in Singapore. Include any unit number in the address.",
            "button_label": "Save address",
            "back_url": reverse("checkout" if return_checkout else "addresses"),
            "return_checkout": return_checkout,
        },
    )


def address_delete(request, pk):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    address = get_object_or_404(Address, pk=pk, customer=request.user.customer)
    if request.method == "POST":
        address.delete()
        request.session.pop("checkout_review", None)
        messages.success(
            request,
            "Address deleted. Previous orders keep their saved delivery details.",
        )
        return redirect("addresses")
    return render(
        request,
        "marketplace/confirm.html",
        {
            "title": "Delete this address?",
            "description": str(address),
            "button_label": "Delete address",
            "back_url": reverse("addresses"),
        },
    )


def cart(request):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    return render(request, "marketplace/cart.html", cart_summary(request.user.customer))


def cart_add(request, pk):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    product = get_object_or_404(active_products(), pk=pk)
    form = VariantSelectionForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        variant = product.variants.filter(
            size=data["size"], colour=data["colour"]
        ).first()
        if not variant:
            messages.error(
                request,
                "That size and colour combination is unavailable. Please choose an available variant.",
            )
        else:
            try:
                add_to_cart(request.user.customer, variant.pk, data["quantity"])
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                request.session.pop("checkout_review", None)
                messages.success(
                    request,
                    f"{product.name} was added to your bag. You can review it or continue shopping.",
                )
                return redirect("cart")
    else:
        messages.error(
            request,
            "Select a size and colour, and enter a positive whole-number quantity.",
        )
    params = {k: request.POST.get(k, "") for k in ["size", "colour", "quantity"]}
    return redirect(reverse("product_detail", args=[pk]) + "?" + urlencode(params))


def cart_update(request, pk):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    get_object_or_404(CartItem, pk=pk, cart__customer=request.user.customer)
    if request.POST.get("action") == "remove":
        quantity = 0
    else:
        form = QuantityForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a positive whole-number quantity.")
            return redirect("cart")
        quantity = form.cleaned_data["quantity"]
    try:
        update_cart_item(request.user.customer, pk, quantity)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        request.session.pop("checkout_review", None)
        messages.success(request, "Bag updated.")
    return redirect("cart")


def checkout(request):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    customer = request.user.customer

    if request.method == "POST":
        token_text = request.POST.get("checkout_token", "")
        try:
            token = uuid.UUID(token_text)
        except (ValueError, TypeError, AttributeError):
            token = None
        replay = request.session.get("checkout_replay", {})
        existing = (
            Order.objects.filter(customer=customer, pk=replay.get("order_id")).first()
            if token and replay.get("token") == token_text
            else None
        )
        if existing:
            return redirect("order_confirmation", pk=existing.pk)
        review = request.session.get("checkout_review", {})
        if not token or review.get("token") != token_text:
            messages.error(
                request,
                "This checkout review has expired. Please review your current purchase.",
            )
            return redirect("checkout")
        if request.POST.get("action") == "decline":
            messages.error(
                request,
                "Demo payment declined. No order was placed, no stock changed, and your bag is unchanged. Return to review and retry.",
            )
            return redirect(
                reverse("checkout") + "?" + urlencode({"address": review["address_id"]})
            )
        if request.POST.get("action") != "place":
            messages.error(request, "Choose a valid demo checkout action.")
            return redirect("checkout")
        try:
            order = place_order(customer, review["address_id"], review["details"])
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("checkout")
        request.session["checkout_replay"] = {
            "token": token_text,
            "order_id": order.pk,
        }
        request.session.pop("checkout_review", None)
        return redirect("order_confirmation", pk=order.pk)

    summary = cart_summary(customer)
    if not summary["items"]:
        messages.info(request, "Add a piece to your bag before checkout.")
        return redirect("cart")
    if not summary["valid"]:
        messages.error(
            request, "Resolve the unavailable items in your bag before checkout."
        )
        return redirect("cart")
    addresses = customer.addresses.all()
    selected_id = request.GET.get(
        "address", str(request.session.get("selected_address", ""))
    )
    valid_id = (
        selected_id.isascii() and selected_id.isdecimal() and len(selected_id) <= 18
    )
    selected = addresses.filter(pk=int(selected_id)).first() if valid_id else None
    if not selected:
        selected = addresses.first()
    review = None
    if selected:
        request.session["selected_address"] = selected.pk
        review = {
            "token": str(uuid.uuid4()),
            "address_id": selected.pk,
            "details": review_details(customer, selected),
        }
        request.session["checkout_review"] = review
    summary.update(
        {
            "addresses": addresses,
            "selected_address": selected,
            "checkout_token": review["token"] if review else "",
        }
    )
    return render(request, "marketplace/checkout.html", summary)


def orders(request):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access

    queryset = request.user.customer.orders.all()
    status = request.GET.get("status", "")
    if status in [value for value, label in Order.STATUS_CHOICES]:
        queryset = queryset.filter(order_status=status)
    return render(
        request,
        "marketplace/orders.html",
        {
            "page_obj": Paginator(queryset, 12).get_page(request.GET.get("page")),
            "statuses": Order.STATUS_CHOICES,
            "selected_status": status,
        },
    )


def owned_order(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer__account").prefetch_related(
            "seller_orders__items"
        ),
        pk=pk,
    )
    if request.user.role != "ADMIN" and order.customer.account_id != request.user.pk:
        raise PermissionDenied
    return order


def order_detail(request, pk, confirmation=False, printable=False):
    access = check_access(request, ["CUSTOMER", "ADMIN"])
    if access is not None:
        return access

    order = owned_order(request, pk)
    return render(
        request,
        (
            "marketplace/order_print.html"
            if printable
            else "marketplace/order_detail.html"
        ),
        {
            "order": order,
            "confirmation": confirmation,
        },
    )


def order_cancel(request, pk):
    access = check_access(request, ["CUSTOMER", "ADMIN"])
    if access is not None:
        return access

    order = owned_order(request, pk)
    if request.method == "POST":
        try:
            cancel_order(order.pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(
                request,
                "Order cancelled. Stock was restored once and the demo payment is marked refunded.",
            )
        return redirect("order_detail", pk=order.pk)
    return render(
        request,
        "marketplace/confirm.html",
        {
            "title": f"Cancel order {order.reference()}?",
            "description": "This cancels every retailer portion and restores all purchased quantities. Cancellation is available only before any portion ships.",
            "order": order,
            "button_label": "Cancel entire order",
            "back_url": reverse("order_detail", args=[order.pk]),
        },
    )


def order_buy_again(request, pk):
    access = check_access(request, ["CUSTOMER"])
    if access is not None:
        return access
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    order = owned_order(request, pk)
    added, skipped = [], []
    for portion in order.seller_orders.all():
        for item in portion.items.all():
            try:
                add_to_cart(request.user.customer, item.variant_id, item.quantity)
            except ValidationError:
                skipped.append(item.variant.product.name)
            else:
                added.append(item.variant.product.name)
    request.session.pop("checkout_review", None)
    if added:
        messages.success(
            request,
            "Available items added using current prices. Please review your bag.",
        )
    if skipped:
        messages.warning(
            request, "Unavailable or insufficient stock; skipped: " + ", ".join(skipped)
        )
    return redirect("cart")


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)


def public_products():
    return (
        active_products()
        .select_related("seller", "seller__account", "category")
        .prefetch_related("variants", "productstyle_set__style")
    )


def public_sellers():
    return Seller.objects.filter(approval_status="APPROVED")


def _recommendations(request, queryset=None, preview_style=None, preview_collection=None):
    from .recommendations import recommend_products

    customer = (
        getattr(request.user, "customer", None)
        if request.user.is_authenticated
        else None
    )
    return recommend_products(
        customer,
        queryset=queryset,
        preview_style=preview_style,
        preview_collection=preview_collection,
    )


def home(request):
    selection = _recommendations(request, public_products())
    return render(
        request,
        "marketplace/home.html",
        {
            "selection": selection,
            "products": selection["products"][:3],
            "active_nav": "home",
        },
    )


def filter_catalogue(request, queryset, available_only=False):
    from .recommendations import COLLECTION_LABELS, filter_product_collection

    query = request.GET.get("q", "").strip()
    selected = {}
    errors = []
    for field in ["category", "style", "seller", "size", "colour"]:
        selected[field] = request.GET.getlist(field)
    selected_collection = "ALL"
    if not available_only:
        selected_collection = request.GET.get("collection", "ALL") or "ALL"
        if (
            selected_collection not in COLLECTION_LABELS
            or len(request.GET.getlist("collection")) > 1
        ):
            errors.append("Choose a single available clothing collection.")
            selected_collection = "ALL"
        else:
            queryset = filter_product_collection(queryset, selected_collection)

    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(seller__store_name__icontains=query)
        )
    for key, lookup in [
        ("category", "category_id__in"),
        ("style", "productstyle__style_id__in"),
        ("seller", "seller_id__in"),
    ]:
        if selected[key]:
            valid_ids = []
            for value in selected[key]:
                if value.isascii() and value.isdecimal() and len(value) <= 19:
                    number = int(value)
                    if 0 < number <= 9223372036854775807:
                        valid_ids.append(number)
            queryset = queryset.filter(**{lookup: valid_ids})

    price_values = {}
    for name, lookup in [("min_price", "price__gte"), ("max_price", "price__lte")]:
        value = request.GET.get(name, "").strip()
        price_values[name] = value
        if value:
            try:
                price = Decimal(value)
                if not price.is_finite() or price < 0 or price > Decimal("99999999.99"):
                    raise InvalidOperation
                queryset = queryset.filter(**{lookup: price})
            except (InvalidOperation, ValueError):
                error = "Enter a valid non-negative price."
                if error not in errors:
                    errors.append(error)
    if not errors and all(price_values.values()):
        if Decimal(price_values["min_price"]) > Decimal(price_values["max_price"]):
            errors.append("The minimum price must not exceed the maximum price.")
    if errors:
        queryset = queryset.none()

    if (
        selected["size"]
        or selected["colour"]
        or request.GET.get("stock") == "1"
        or available_only
    ):
        variants = ProductVariant.objects.all()
        if selected["size"]:
            variants = variants.filter(size__in=selected["size"])
        if selected["colour"]:
            variants = variants.filter(colour__in=selected["colour"])
        if request.GET.get("stock") == "1" or available_only:
            variants = variants.filter(stock_quantity__gt=0)
        queryset = queryset.filter(pk__in=variants.values("product_id"))

    queryset = queryset.distinct()
    return queryset, {
        "query": query,
        "selected": selected,
        "filter_errors": errors,
        "min_price": price_values["min_price"],
        "max_price": price_values["max_price"],
        "stock_only": request.GET.get("stock") == "1",
        "selected_collection": selected_collection,
        "collection_choices": list(COLLECTION_LABELS.items()),
    }


def catalogue_url(path, query_params, remove=()):
    params = query_params.copy()
    for name in remove:
        params.pop(name, None)
    query = params.urlencode()
    if query:
        return path + "?" + query
    return path


def catalogue_context(request, queryset, personalised=False):
    queryset, context = filter_catalogue(request, queryset, available_only=personalised)
    sort = request.GET.get("sort", "")
    ordering = {
        "name": ("name", "pk"),
        "price_asc": ("price", "name", "pk"),
        "price_desc": ("-price", "name", "pk"),
    }
    selection = None
    comparison_products = []
    ranked_examples = []
    preview_style = ""
    preview_collection = None
    if personalised:
        from .recommendations import COLLECTION_LABELS, STYLE_SLUGS

        preview_style = request.GET.get("preview_style", "")
        if preview_style and (
            preview_style not in STYLE_SLUGS
            or len(request.GET.getlist("preview_style")) != 1
        ):
            context["filter_errors"].append(
                "Choose a single available style from the preview buttons."
            )
            preview_style = ""
        raw_collection = request.GET.get("preview_collection", "")
        if "preview_collection" in request.GET and (
            len(request.GET.getlist("preview_collection")) != 1
            or (raw_collection and raw_collection not in COLLECTION_LABELS)
        ):
            context["filter_errors"].append(
                "Choose a single available clothing selection."
            )
        else:
            preview_collection = raw_collection or None
        selection = _recommendations(
            request,
            queryset,
            preview_style=preview_style or None,
            preview_collection=preview_collection,
        )
        if sort not in ordering:
            sort = "recommended" if selection["personalised"] else "name"
        alphabetical_products = sorted(
            selection["products"], key=lambda product: (product.name.lower(), product.pk)
        )
        if sort == "recommended":
            products = selection["products"]
        else:
            products = alphabetical_products.copy()
            if sort in ["price_asc", "price_desc"]:
                products.sort(key=lambda product: product.price, reverse=sort == "price_desc")
        if selection["personalised"]:
            comparison_products = alphabetical_products[:3]
            ranked_examples = selection["products"][:3]
    else:
        if sort not in ordering:
            sort = "name"
        products = queryset.order_by(*ordering[sort])

    page = Paginator(products, 12).get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    if personalised:
        if not preview_style:
            query_params.pop("preview_style", None)
        query_params.pop("collection", None)
        if preview_collection is None:
            query_params.pop("preview_collection", None)
    preserved_previews = {}
    if preview_style:
        preserved_previews["preview_style"] = preview_style
    if preview_collection is not None:
        preserved_previews["preview_collection"] = preview_collection
    clear_filters_url = request.path
    if preserved_previews:
        clear_filters_url += "?" + urlencode(preserved_previews)
    saved_collection_url = catalogue_url(request.path, query_params, ["preview_collection"])
    saved_style_url = catalogue_url(request.path, query_params, ["preview_style"])
    comparison_params = query_params.copy()
    comparison_params.pop("preview_style", None)
    comparison_params.pop("preview_collection", None)
    if selection:
        comparison_params["collection"] = selection["collection"]
    comparison_params["sort"] = "name"
    comparison_params["stock"] = "1"
    catalogue_comparison_url = catalogue_url(reverse("catalogue"), comparison_params)
    style_previews = []
    if personalised:
        for slug in STYLE_SLUGS:
            preview_params = query_params.copy()
            preview_params["preview_style"] = slug
            preview_params["sort"] = "recommended"
            style_previews.append(
                {
                    "slug": slug,
                    "name": slug.title(),
                    "url": catalogue_url(request.path, preview_params) + "#clothing-results",
                }
            )
    collection_hidden_fields = []
    for name, values in query_params.lists():
        if name != "preview_collection":
            for value in values:
                collection_hidden_fields.append((name, value))
    active_variants = ProductVariant.objects.filter(product__in=public_products())
    context.update(
        {
            "page_obj": page,
            "products": page.object_list,
            "product_count": page.paginator.count,
            "query_params": query_params.urlencode(),
            "pagination_anchor": "#clothing-results",
            "sort": sort,
            "selection": selection,
            "categories": Category.objects.all(),
            "styles": Style.objects.all(),
            "sellers": public_sellers(),
            "sizes": active_variants.order_by("size")
            .values_list("size", flat=True)
            .distinct(),
            "colours": active_variants.order_by("colour")
            .values_list("colour", flat=True)
            .distinct(),
            "has_filters": any(
                request.GET.getlist(k)
                for k in [
                    "q",
                    "category",
                    "style",
                    "seller",
                    "size",
                    "colour",
                    "stock",
                    "min_price",
                    "max_price",
                ]
            ) or (not personalised and context["selected_collection"] != "ALL"),
            "active_nav": "for_you" if personalised else "shop",
            "is_for_you": personalised,
            "preview_style": preview_style,
            "preview_collection": preview_collection,
            "style_previews": style_previews,
            "collection_hidden_fields": collection_hidden_fields,
            "saved_collection_url": saved_collection_url,
            "saved_style_url": saved_style_url,
            "clear_filters_url": clear_filters_url,
            "catalogue_comparison_url": catalogue_comparison_url,
            "comparison_products": comparison_products,
            "ranked_examples": ranked_examples,
        }
    )
    return context


def catalogue(request):
    context = catalogue_context(request, public_products())
    context.update(
        {"page_title": "A considered wardrobe", "eyebrow": "Shop / All clothing"}
    )
    return render(request, "marketplace/catalogue.html", context)


def for_you(request):
    context = catalogue_context(request, public_products(), personalised=True)
    selection = context["selection"]
    context.update(
        {
            "page_title": (
                "Selected for your preferences"
                if selection["personalised"] and not selection["preview"]
                else "Find your style"
            ),
            "eyebrow": "Personal discovery",
            "active_nav": "for_you",
        }
    )
    return render(request, "marketplace/catalogue.html", context)


def brands(request):
    sellers = public_sellers().order_by("store_name")
    query = request.GET.get("q", "").strip()
    if query:
        sellers = sellers.filter(
            Q(store_name__icontains=query) | Q(store_description__icontains=query)
        )
    return render(
        request,
        "marketplace/brands.html",
        {"sellers": sellers, "query": query, "active_nav": "brands"},
    )


def brand_detail(request, pk):
    seller = get_object_or_404(public_sellers(), pk=pk)
    context = catalogue_context(request, public_products().filter(seller=seller))
    context.update(
        {
            "brand": seller,
            "page_title": seller.store_name,
            "eyebrow": "Brands / " + seller.store_name,
            "active_nav": "brands",
        }
    )
    return render(request, "marketplace/catalogue.html", context)


def product_detail(request, pk):
    product = get_object_or_404(public_products(), pk=pk)
    if request.method == "POST":
        choices = {
            key: request.POST.get(key, "") for key in ["size", "colour", "quantity"]
        }
        return redirect(reverse("product_detail", args=[pk]) + "?" + urlencode(choices))
    variants = list(product.variants.all())
    size = request.GET.get("size", "")
    colour = request.GET.get("colour", "")
    selected_variant = next(
        (v for v in variants if v.size == size and v.colour == colour), None
    )
    from .sizing import product_size_guidance

    customer = (
        getattr(request.user, "customer", None)
        if request.user.is_authenticated
        else None
    )
    height = customer.height if customer is not None else None
    weight = customer.weight if customer is not None else None
    size_guidance = product_size_guidance(product, height, weight, colour=colour)
    return render(
        request,
        "marketplace/product_detail.html",
        {
            "product": product,
            "variants": variants,
            "sizes": list(dict.fromkeys(v.size for v in variants)),
            "colours": list(dict.fromkeys(v.colour for v in variants)),
            "selected_size": size,
            "selected_colour": colour,
            "selected_variant": selected_variant,
            "selection_made": bool(size and colour),
            "quantity": request.GET.get("quantity", "1"),
            "size_guidance": size_guidance,
            "sizing_profile_available": height is not None and weight is not None,
            "active_nav": "shop",
        },
    )


def about(request):
    return render(request, "marketplace/about.html", {"active_nav": "about"})


def help_page(request):
    return render(request, "marketplace/help.html")


LOW_STOCK_THRESHOLD = 5


def record_id(value):
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError):
        raise Http404("This record could not be found.")
    if not 0 < number <= 9223372036854775807:
        raise Http404("This record could not be found.")
    return number


def workspace(request, template, context=None):
    context = context or {}
    context["is_operations"] = request.user.role == "ADMIN"
    context["workspace_title"] = (
        "Operations" if context["is_operations"] else "Seller workspace"
    )
    query = request.GET.copy()
    query.pop("page", None)
    context["query_params"] = query.urlencode()
    return render(request, f"marketplace/manage/{template}.html", context)


def report_totals(portions):
    totals = {
        "sales": Decimal("0.00"),
        "quoted": Decimal("0.00"),
        "recognised": Decimal("0.00"),
        "estimated_net": Decimal("0.00"),
    }
    for portion in portions:
        totals["sales"] += portion.subtotal
        totals["quoted"] += portion.commission_amount
        totals["recognised"] += portion.recognised_commission()
        totals["estimated_net"] += portion.net_revenue()
    return totals


def seller_status(request):
    access = check_access(request, ["SELLER"])
    if access is not None:
        return access

    seller = get_object_or_404(Seller, account=request.user)
    if seller.can_trade():
        return redirect("seller_dashboard")
    return workspace(request, "seller_status", {"seller": seller})


def seller_dashboard(request):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    seller = request.user.seller
    cards = [
        (
            "Active products",
            seller.products.filter(is_active=True, approval_status="APPROVED").count(),
            reverse("seller_products") + "?status=active",
        ),
        (
            "Low-stock variants",
            ProductVariant.objects.filter(
                product__seller=seller, stock_quantity__range=(1, 5)
            ).count(),
            reverse("seller_inventory") + "?stock=low",
        ),
        (
            "Processing portions",
            seller.seller_orders.filter(fulfilment_status="PROCESSING").count(),
            reverse("seller_orders") + "?status=PROCESSING",
        ),
    ]
    totals = report_totals(seller.seller_orders.select_related("order"))
    return workspace(
        request,
        "dashboard",
        {
            "heading": seller.store_name,
            "cards": cards,
            "totals": totals,
            "recent_portions": seller.seller_orders.select_related("order").order_by(
                "-order__order_date"
            )[:5],
        },
    )


def seller_profile(request):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    seller = request.user.seller
    form = StoreProfileForm(request.POST or None, instance=seller)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
            messages.success(request, "Your store profile has been updated.")
            return redirect("seller_profile")
        except IntegrityError:
            form.add_error(
                "store_name",
                "This store name was just registered. Choose another name.",
            )
    return workspace(
        request,
        "form",
        {
            "heading": "Store profile",
            "form": form,
            "intro": "Your commission rate and approval status are managed by marketplace staff.",
        },
    )


def operations_dashboard(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    recognised = Decimal("0.00")
    delivered_portions = SellerOrder.objects.filter(
        fulfilment_status="DELIVERED", order__payment_status="PAID"
    )
    for portion in delivered_portions:
        recognised += portion.commission_amount
    cards = [
        (
            "Pending seller applications",
            Seller.objects.filter(approval_status="PENDING").count(),
            reverse("operations_sellers") + "?status=PENDING",
        ),
        (
            "Active retailers",
            Seller.objects.filter(approval_status="APPROVED").count(),
            reverse("operations_sellers") + "?status=APPROVED",
        ),
        (
            "Active products",
            active_products().count(),
            reverse("operations_products") + "?status=active",
        ),
        (
            "Customer accounts",
            Customer.objects.count(),
            reverse("operations_customers"),
        ),
        (
            "Processing portions",
            SellerOrder.objects.filter(fulfilment_status="PROCESSING").count(),
            reverse("operations_orders") + "?portion_status=PROCESSING",
        ),
        (
            "Low-stock variants",
            ProductVariant.objects.filter(stock_quantity__range=(1, 5)).count(),
            reverse("operations_inventory") + "?stock=low",
        ),
        (
            "Recognised commission (SGD)",
            f"{recognised:.2f}",
            reverse("operations_commissions") + "?status=DELIVERED",
        ),
    ]
    return workspace(
        request,
        "dashboard",
        {
            "heading": "Marketplace overview",
            "cards": cards,
            "pending_products": Product.objects.filter(
                approval_status="PENDING"
            ).select_related("seller"),
            "recent_portions": SellerOrder.objects.filter(
                fulfilment_status="PROCESSING"
            ).select_related("order", "seller")[:5],
        },
    )


def operations_sellers(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    sellers = Seller.objects.select_related("account")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if q:
        sellers = sellers.filter(
            Q(store_name__icontains=q)
            | Q(email__icontains=q)
            | Q(account__username__icontains=q)
        )
    if status in [value for value, label in Seller.STATUS_CHOICES]:
        sellers = sellers.filter(approval_status=status)
    return workspace(
        request,
        "sellers",
        {
            "sellers": sellers,
            "q": q,
            "selected_status": status,
            "statuses": Seller.STATUS_CHOICES,
        },
    )


def operations_seller_create(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    form = StaffSellerCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                account = create_account(
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["account_email"],
                    password=form.cleaned_data["password"],
                    role="SELLER",
                )
                seller = form.save(commit=False)
                seller.account = account
                seller.save()
            messages.success(
                request,
                "Retailer created as pending. Review and approve the application below.",
            )
            return redirect("operations_seller_edit", pk=seller.pk)
        except IntegrityError:
            form.add_error(
                None,
                "This account or store name was just registered. Choose another value.",
            )
    return workspace(request, "form", {"heading": "New retailer", "form": form})


def operations_seller_edit(request, pk):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    seller = get_object_or_404(Seller.objects.select_related("account"), pk=pk)
    form = StaffSellerForm(
        (
            request.POST
            if request.method == "POST" and request.POST.get("action") == "save"
            else None
        ),
        instance=seller,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save" and form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(
                    request,
                    "Retailer details saved. Historical commission rates are unchanged.",
                )
                return redirect("operations_seller_edit", pk=pk)
            except IntegrityError:
                form.add_error(
                    "store_name",
                    "This store name was just registered. Choose another name.",
                )
        elif action in ["approve", "reject", "suspend", "reactivate"]:
            transitions = {
                "approve": ("PENDING", "APPROVED"),
                "reject": ("PENDING", "REJECTED"),
                "suspend": ("APPROVED", "SUSPENDED"),
                "reactivate": ("SUSPENDED", "APPROVED"),
            }
            expected, target = transitions[action]
            reason = request.POST.get("reason", "").strip()
            if request.POST.get("confirm") != "yes":
                messages.error(
                    request, "Confirm the retailer status change before continuing."
                )
            elif action == "reject" and not reason:
                messages.error(
                    request, "Enter a reason for rejecting this application."
                )
            elif request.POST.get("expected_status") != expected:
                messages.error(
                    request, "The application changed. Review its latest status."
                )
            else:
                updated = Seller.objects.filter(pk=pk, approval_status=expected).update(
                    approval_status=target,
                    rejection_reason=reason if action == "reject" else "",
                    reviewed_by=get_admin_profile(request.user),
                )
                if updated:
                    messages.success(
                        request, f"Retailer status changed to {target.lower()}."
                    )
                else:
                    messages.error(
                        request,
                        "The retailer was already reviewed or changed. Its latest status is shown.",
                    )
            return redirect("operations_seller_edit", pk=pk)
    return workspace(request, "seller_detail", {"seller": seller, "form": form})


def product_list(request, staff=False):
    products = Product.objects.select_related("seller", "category").prefetch_related(
        "variants"
    )
    if not staff:
        products = products.filter(seller=request.user.seller)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if q:
        products = products.filter(
            Q(name__icontains=q)
            | Q(seller__store_name__icontains=q)
            | Q(category__name__icontains=q)
        )
    if status == "active":
        products = active_products(products)
    elif status == "archived":
        products = products.filter(is_active=False)
    elif status in [value for value, label in Product.STATUS_CHOICES]:
        products = products.filter(approval_status=status)
    return workspace(
        request,
        "products",
        {
            "page_obj": Paginator(products, 20).get_page(request.GET.get("page")),
            "q": q,
            "selected_status": status,
            "statuses": Product.STATUS_CHOICES,
        },
    )


def seller_products(request):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    return product_list(request)


def operations_products(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return product_list(request, staff=True)


def product_editor(request, pk=None, staff=False):
    products = (
        Product.objects.all()
        if staff
        else Product.objects.filter(seller=request.user.seller)
    )
    product = get_object_or_404(products, pk=pk) if pk else None
    form_class = StaffProductCreateForm if staff and product is None else ProductForm
    action = request.POST.get("action", "save")
    form = form_class(
        request.POST if request.method == "POST" and action == "save" else None,
        request.FILES if request.method == "POST" and action == "save" else None,
        instance=product,
    )
    edit_route = "operations_product_edit" if staff else "seller_product_edit"
    list_route = "operations_products" if staff else "seller_products"
    if request.method == "POST":
        if action == "save" and form.is_valid():
            record = form.save(commit=False)
            if product is None and not staff:
                record.seller = request.user.seller
            if product:
                record.save(
                    update_fields=[
                        "name",
                        "description",
                        "category",
                        "collection",
                        "price",
                        "image",
                    ]
                )
            else:
                record.save()
            form.save_styles(record)
            messages.success(
                request,
                "Product details saved. Add variants before requesting publication.",
            )
            return redirect(edit_route, pk=record.pk)
        elif product and action in [
            "publish",
            "archive",
            "submit",
            "approve",
            "reject",
            "delete",
        ]:
            if request.POST.get("confirm") != "yes":
                messages.error(
                    request, "Confirm this product action before continuing."
                )
            elif action == "archive":
                Product.objects.filter(pk=pk).update(is_active=False)
                messages.success(
                    request,
                    "Product archived. Order prices and quantities are retained.",
                )
            elif action == "delete":
                if product.variants.filter(
                    Q(cart_items__isnull=False) | Q(order_items__isnull=False)
                ).exists():
                    messages.error(
                        request,
                        "A bag or order references this product. Archive it instead.",
                    )
                else:
                    try:
                        with transaction.atomic():
                            product.variants.all().delete()
                            product.delete()
                        messages.success(request, "Unreferenced product deleted.")
                        return redirect(list_route)
                    except ProtectedError:
                        messages.error(
                            request,
                            "This product became referenced. Archive it instead.",
                        )
            elif action == "reject":
                if not staff:
                    raise PermissionDenied
                reason = request.POST.get("reason", "").strip()
                if not reason:
                    messages.error(request, "Enter a rejection reason.")
                elif request.POST.get("expected_status") != product.approval_status:
                    messages.error(
                        request, "The product status changed. Review it again."
                    )
                else:
                    updated = Product.objects.filter(
                        pk=pk, approval_status=product.approval_status
                    ).update(
                        approval_status="REJECTED",
                        is_active=False,
                        rejection_reason=reason,
                        reviewed_by=get_admin_profile(request.user),
                    )
                    messages.success(
                        request,
                        (
                            "Product rejected."
                            if updated
                            else "Product status was already changed."
                        ),
                    )
            else:
                ready = (
                    product.seller.can_trade()
                    and product.variants.exists()
                    and product.get_styles().exists()
                )
                if not ready:
                    messages.error(
                        request,
                        "Publication needs an approved retailer, at least one variant and a style.",
                    )
                elif action == "submit":
                    if product.approval_status in ["DRAFT", "REJECTED"]:
                        Product.objects.filter(
                            pk=pk, approval_status=product.approval_status
                        ).update(
                            approval_status="PENDING",
                            is_active=False,
                            rejection_reason="",
                        )
                        messages.success(
                            request, "Product submitted for staff approval."
                        )
                    else:
                        messages.error(
                            request,
                            "Only a draft or rejected product can be submitted.",
                        )
                elif action == "approve":
                    if not staff:
                        raise PermissionDenied
                    expected = request.POST.get("expected_status")
                    if expected != product.approval_status:
                        messages.error(request, "The product changed. Review it again.")
                    else:
                        updated = Product.objects.filter(
                            pk=pk, approval_status=expected
                        ).update(
                            approval_status="APPROVED",
                            is_active=True,
                            reviewed_by=get_admin_profile(request.user),
                            rejection_reason="",
                        )
                        messages.success(
                            request,
                            (
                                "Product approved and published."
                                if updated
                                else "The product status changed. Review it again."
                            ),
                        )
                elif product.approval_status == "APPROVED":
                    Product.objects.filter(pk=pk).update(is_active=True)
                    messages.success(request, "Product published.")
                else:
                    messages.error(
                        request,
                        "Staff approval is needed before this product can be published.",
                    )
            return redirect(edit_route, pk=pk)
    return workspace(
        request,
        "product_editor",
        {
            "form": form,
            "product": product,
            "heading": product.name if product else "Add product",
            "variants": product.variants.all() if product else [],
        },
    )


def seller_product_create(request):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    return product_editor(request)


def seller_product_edit(request, pk):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    return product_editor(request, pk)


def operations_product_create(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return product_editor(request, staff=True)


def operations_product_edit(request, pk):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return product_editor(request, pk, staff=True)


def variant_editor(request, pk, staff=False, creating=False):
    products = (
        Product.objects.all()
        if staff
        else Product.objects.filter(seller=request.user.seller)
    )
    if creating:
        product = get_object_or_404(products, pk=pk)
        variant = None
    else:
        variants = ProductVariant.objects.filter(product__in=products).select_related(
            "product"
        )
        variant = get_object_or_404(variants, pk=pk)
        product = variant.product
    form = VariantForm(request.POST or None, instance=variant, product=product)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                record = form.save(commit=False)
                if variant:
                    ProductVariant.objects.filter(pk=variant.pk).update(
                        stock_quantity=F("stock_quantity")
                    )
                record.full_clean()

                if variant:
                    record.save(update_fields=["size", "colour", "sku"])
                else:
                    record.save()
            messages.success(request, "Variant saved.")
            return redirect(
                "operations_product_edit" if staff else "seller_product_edit",
                pk=product.pk,
            )
        except (ValidationError, IntegrityError) as error:
            form.add_error(
                None,
                (
                    error
                    if isinstance(error, ValidationError)
                    else "This SKU or size-colour combination already exists."
                ),
            )
    return workspace(
        request,
        "form",
        {
            "heading": f"{'Add' if creating else 'Edit'} variant / {product.name}",
            "form": form,
            "intro": "Existing stock is adjusted from Inventory. Referenced variant identities are locked.",
        },
    )


def seller_variant_create(request, pk):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    return variant_editor(request, pk, creating=True)


def seller_variant_edit(request, pk):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    return variant_editor(request, pk)


def operations_variant_create(request, pk):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return variant_editor(request, pk, staff=True, creating=True)


def operations_variant_edit(request, pk):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return variant_editor(request, pk, staff=True)


def inventory_list(request, staff=False):
    variants = ProductVariant.objects.select_related("product", "product__seller")
    if not staff:
        variants = variants.filter(product__seller=request.user.seller)
    q = request.GET.get("q", "").strip()
    stock = request.GET.get("stock", "")
    if q:
        variants = variants.filter(
            Q(sku__icontains=q)
            | Q(product__name__icontains=q)
            | Q(product__seller__store_name__icontains=q)
        )
    if stock == "low":
        variants = variants.filter(stock_quantity__range=(1, LOW_STOCK_THRESHOLD))
    elif stock == "soldout":
        variants = variants.filter(stock_quantity=0)
    return workspace(
        request, "inventory", {"variants": variants, "q": q, "selected_stock": stock}
    )


def seller_inventory(request):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    return inventory_list(request)


def operations_inventory(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return inventory_list(request, staff=True)


def inventory_adjust(request, pk, staff=False):
    variants = ProductVariant.objects.select_related("product", "product__seller")
    if not staff:
        variants = variants.filter(product__seller=request.user.seller)
    variant = get_object_or_404(variants, pk=pk)
    form = InventoryAdjustmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            adjust_stock(variant.pk, form.cleaned_data["delta"])
            messages.success(
                request, "Stock adjusted using the latest stored quantity."
            )
            return redirect("operations_inventory" if staff else "seller_inventory")
        except ValidationError as error:
            form.add_error(None, error)
    return workspace(
        request,
        "form",
        {
            "heading": f"Adjust inventory / {variant.sku}",
            "form": form,
            "intro": f"{variant.product.name} / {variant.colour} / {variant.size}. Current stock: {variant.stock_quantity}. No inventory movement log is stored.",
        },
    )


def seller_inventory_adjust(request, pk):
    access = check_access(request, ["SELLER"], approved_seller=True)
    if access is not None:
        return access

    return inventory_adjust(request, pk)


def operations_inventory_adjust(request, pk):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return inventory_adjust(request, pk, staff=True)


def seller_orders(request):
    access = check_access(request, ["SELLER"])
    if access is not None:
        return access

    seller = get_object_or_404(Seller, account=request.user)
    portions = (
        seller.seller_orders.select_related("order")
        .prefetch_related("items")
        .order_by("-order__order_date")
    )
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if q:
        reference = q.upper().removeprefix("W-")
        portions = (
            portions.filter(order_id=int(reference))
            if reference.isdigit()
            else portions.none()
        )
    if status in [value for value, label in SellerOrder.STATUS_CHOICES]:
        portions = portions.filter(fulfilment_status=status)
    return workspace(
        request,
        "seller_orders",
        {
            "portions": portions,
            "seller": seller,
            "q": q,
            "selected_status": status,
            "statuses": SellerOrder.STATUS_CHOICES,
        },
    )


def seller_order_detail(request, pk):
    access = check_access(request, ["SELLER"])
    if access is not None:
        return access

    seller = get_object_or_404(Seller, account=request.user)
    portion = get_object_or_404(
        SellerOrder.objects.select_related("order", "seller"), pk=pk, seller=seller
    )
    if request.method == "POST":
        if not seller.can_trade():
            raise PermissionDenied(
                "This store cannot currently update fulfilment. Marketplace staff can assist."
            )
        try:
            advance_fulfilment(
                portion.pk,
                request.POST.get("expected_status", ""),
                request.POST.get("target_status", ""),
            )
            messages.success(request, "Fulfilment status updated.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect("seller_order_detail", pk=pk)
    return workspace(
        request,
        "order_detail",
        {
            "order": portion.order,
            "portions": [portion],
            "seller": seller,
            "can_fulfil": seller.can_trade(),
        },
    )


def operations_orders(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    orders = Order.objects.select_related("customer__account").prefetch_related(
        "seller_orders"
    )
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    portion_status = request.GET.get("portion_status", "")
    if q:
        query = (
            Q(customer__account__username__icontains=q)
            | Q(customer__account__email__icontains=q)
            | Q(seller_orders__seller__store_name__icontains=q)
        )
        reference = q.upper().removeprefix("W-")
        if reference.isdigit():
            query |= Q(pk=int(reference))
        orders = orders.filter(query)
    if status in [value for value, label in Order.STATUS_CHOICES]:
        orders = orders.filter(order_status=status)
    if portion_status in [value for value, label in SellerOrder.STATUS_CHOICES]:
        orders = orders.filter(seller_orders__fulfilment_status=portion_status)
    dates = ReportFilterForm(request.GET or None)
    dates.fields.pop("seller")
    dates.fields.pop("status")
    if dates.is_bound and dates.is_valid():
        if dates.cleaned_data["start"]:
            orders = orders.filter(order_date__date__gte=dates.cleaned_data["start"])
        if dates.cleaned_data["end"]:
            orders = orders.filter(order_date__date__lte=dates.cleaned_data["end"])
    return workspace(
        request,
        "orders",
        {
            "page_obj": Paginator(orders.distinct(), 20).get_page(
                request.GET.get("page")
            ),
            "q": q,
            "selected_status": status,
            "statuses": Order.STATUS_CHOICES,
            "date_form": dates,
        },
    )


def operations_order_detail(request, pk):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    order = get_object_or_404(
        Order.objects.select_related("customer__account").prefetch_related(
            "seller_orders__items"
        ),
        pk=pk,
    )
    if request.method == "POST":
        try:
            if request.POST.get("action") == "cancel":
                if request.POST.get("confirm") != "yes":
                    raise ValidationError(
                        "Confirm cancellation of the full order and every retailer portion."
                    )
                cancel_order(order.pk)
                messages.success(
                    request,
                    "Order cancelled and stock restored. Demo payment marked refunded.",
                )
            else:
                portion = get_object_or_404(
                    order.seller_orders, pk=record_id(request.POST.get("portion_id"))
                )
                advance_fulfilment(
                    portion.pk,
                    request.POST.get("expected_status", ""),
                    request.POST.get("target_status", ""),
                )
                messages.success(request, "Fulfilment status updated.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect("operations_order_detail", pk=pk)
    return workspace(
        request,
        "order_detail",
        {"order": order, "portions": order.seller_orders.all(), "can_fulfil": True},
    )


def commission_report(request, staff=False):
    portions = SellerOrder.objects.select_related("order", "seller").order_by(
        "-order__order_date", "pk"
    )
    form = ReportFilterForm(request.GET or None)
    if not staff:
        portions = portions.filter(seller=request.user.seller)
        form.fields.pop("seller")
    if form.is_bound and form.is_valid():
        values = form.cleaned_data
        if staff and values.get("seller"):
            portions = portions.filter(seller=values["seller"])
        if values.get("status"):
            portions = portions.filter(fulfilment_status=values["status"])
        if values.get("start"):
            portions = portions.filter(order__order_date__date__gte=values["start"])
        if values.get("end"):
            portions = portions.filter(order__order_date__date__lte=values["end"])
    elif form.is_bound and not form.is_valid():
        portions = portions.none()
    portions = list(portions)
    totals = report_totals(portions)
    if request.GET.get("export") == "csv" and (not form.is_bound or form.is_valid()):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            'attachment; filename="daehao-collective-commissions.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "Order",
                "Placed",
                "Retailer",
                "Status",
                "Subtotal SGD",
                "Applied rate %",
                "Quoted commission SGD",
                "Recognised commission SGD",
                "Estimated net SGD",
            ]
        )
        for portion in portions:
            name = portion.seller.store_name
            if name.lstrip().startswith(("=", "+", "-", "@")):
                name = "'" + name
            writer.writerow(
                [
                    portion.order.reference(),
                    portion.order.order_date.isoformat(),
                    name,
                    portion.get_fulfilment_status_display(),
                    portion.subtotal,
                    portion.commission_percent(),
                    portion.commission_amount,
                    portion.recognised_commission(),
                    portion.net_revenue(),
                ]
            )
        writer.writerow(
            [
                "TOTALS",
                "",
                "",
                "",
                totals["sales"],
                "",
                totals["quoted"],
                totals["recognised"],
                totals["estimated_net"],
            ]
        )
        return response
    export_query = request.GET.copy()
    export_query["export"] = "csv"
    return workspace(
        request,
        "commissions",
        {
            "portions": portions,
            "form": form,
            "totals": totals,
            "export_query": export_query.urlencode(),
        },
    )


def seller_sales(request):
    access = check_access(request, ["SELLER"])
    if access is not None:
        return access

    get_object_or_404(Seller, account=request.user)
    return commission_report(request)


def operations_commissions(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return commission_report(request, staff=True)


def taxonomy_manager(request, style=False):
    model = Style if style else Category
    form_class = StyleForm if style else TaxonomyForm
    route = "operations_styles" if style else "operations_categories"
    record = None
    raw_id = request.GET.get("edit") or request.POST.get("record_id")
    if raw_id:
        record = get_object_or_404(model, pk=record_id(raw_id))
    action = request.POST.get("action", "save")
    form = form_class(
        request.POST if request.method == "POST" and action == "save" else None,
        instance=record,
    )
    if request.method == "POST":
        if action == "delete" and record:
            if request.POST.get("confirm") != "yes":
                messages.error(request, "Confirm deletion before continuing.")
            else:
                try:
                    record.delete()
                    messages.success(request, "Unreferenced vocabulary value deleted.")
                except ProtectedError:
                    if style:
                        count = (
                            record.productstyle_set.count()
                            + record.customerstylepreference_set.count()
                        )
                        messages.error(
                            request,
                            f"Cannot delete: {count} product or customer preference references use this style.",
                        )
                    else:
                        messages.error(
                            request,
                            f"Cannot delete: {record.products.count()} products use this category.",
                        )
            return redirect(route)
        elif action == "save" and form.is_valid():
            try:
                form.save()
                messages.success(
                    request,
                    "Vocabulary value saved. Check model status after changing a name.",
                )
                return redirect(route)
            except IntegrityError:
                form.add_error("name", "This name was just added. Choose another name.")
    from .recommendations import model_readiness

    readiness = model_readiness()
    unsupported = readiness.get(
        "unsupported_styles" if style else "unsupported_categories", []
    )
    return workspace(
        request,
        "taxonomy",
        {
            "records": model.objects.all(),
            "form": form,
            "record": record,
            "is_style": style,
            "heading": "Fashion styles" if style else "Clothing categories",
            "unsupported": unsupported,
        },
    )


def operations_categories(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return taxonomy_manager(request)


def operations_styles(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    return taxonomy_manager(request, style=True)


def operations_customers(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    customers = Account.objects.filter(role="CUSTOMER")
    q = request.GET.get("q", "").strip()
    if q:
        customers = customers.filter(Q(username__icontains=q) | Q(email__icontains=q))
    customers = customers.order_by("username")
    for customer_account in customers:
        customer_account.order_count = Order.objects.filter(
            customer__account=customer_account
        ).count()
    return workspace(request, "customers", {"customers": customers, "q": q})


def operations_customer_detail(request, pk):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    customer_account = get_object_or_404(Account, pk=pk, role="CUSTOMER")
    if request.method == "POST":
        return HttpResponseNotAllowed(["GET"])
    orders = Order.objects.filter(customer__account=customer_account)
    return workspace(
        request,
        "customer_detail",
        {"customer_account": customer_account, "orders": orders},
    )


def operations_model(request):
    access = check_access(request, ["ADMIN"])
    if access is not None:
        return access

    from .recommendations import model_readiness
    from .sizing import size_model_readiness

    return workspace(
        request,
        "model",
        {"readiness": model_readiness(), "size_readiness": size_model_readiness()},
    )
