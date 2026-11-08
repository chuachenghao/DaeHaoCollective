from django.urls import path

from . import views

urlpatterns = [
    path("account/login/", views.login_view, name="login"),
    path(
        "operations/login/", views.login_view, {"staff": True}, name="operations_login"
    ),
    path("account/register/", views.register, name="register"),
    path("sell/register/", views.register, {"seller": True}, name="seller_register"),
    path("account/logout/", views.logout, name="logout"),
    path("account/", views.account, name="account"),
    path("account/password/", views.password_change, name="password_change"),
    path("account/profile/", views.profile, name="profile"),
    path("account/profile/clear/", views.clear_profile, name="clear_profile"),
    path("account/addresses/", views.addresses, name="addresses"),
    path("account/addresses/add/", views.address_edit, name="address_create"),
    path("account/addresses/<int:pk>/edit/", views.address_edit, name="address_edit"),
    path(
        "account/addresses/<int:pk>/delete/",
        views.address_delete,
        name="address_delete",
    ),
    path("bag/", views.cart, name="cart"),
    path("bag/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("bag/<int:pk>/update/", views.cart_update, name="cart_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("account/orders/", views.orders, name="orders"),
    path("account/orders/<int:pk>/", views.order_detail, name="order_detail"),
    path(
        "account/orders/<int:pk>/confirmation/",
        views.order_detail,
        {"confirmation": True},
        name="order_confirmation",
    ),
    path(
        "account/orders/<int:pk>/print/",
        views.order_detail,
        {"printable": True},
        name="order_print",
    ),
    path("account/orders/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path(
        "account/orders/<int:pk>/buy-again/",
        views.order_buy_again,
        name="order_buy_again",
    ),
    path("", views.home, name="home"),
    path("shop/", views.catalogue, name="catalogue"),
    path("brands/", views.brands, name="brands"),
    path("brands/<int:pk>/", views.brand_detail, name="brand_detail"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("for-you/", views.for_you, name="for_you"),
    path("about/", views.about, name="about"),
    path("help/", views.help_page, name="help"),
    path("seller/", views.seller_dashboard, name="seller_dashboard"),
    path("seller/status/", views.seller_status, name="seller_status"),
    path("seller/profile/", views.seller_profile, name="seller_profile"),
    path("seller/products/", views.seller_products, name="seller_products"),
    path(
        "seller/products/new/",
        views.seller_product_create,
        name="seller_product_create",
    ),
    path(
        "seller/products/<int:pk>/",
        views.seller_product_edit,
        name="seller_product_edit",
    ),
    path(
        "seller/products/<int:pk>/variants/new/",
        views.seller_variant_create,
        name="seller_variant_create",
    ),
    path(
        "seller/variants/<int:pk>/",
        views.seller_variant_edit,
        name="seller_variant_edit",
    ),
    path("seller/inventory/", views.seller_inventory, name="seller_inventory"),
    path(
        "seller/inventory/<int:pk>/",
        views.seller_inventory_adjust,
        name="seller_inventory_adjust",
    ),
    path("seller/orders/", views.seller_orders, name="seller_orders"),
    path(
        "seller/orders/<int:pk>/", views.seller_order_detail, name="seller_order_detail"
    ),
    path("seller/sales/", views.seller_sales, name="seller_sales"),
    path("operations/", views.operations_dashboard, name="operations_dashboard"),
    path("operations/retailers/", views.operations_sellers, name="operations_sellers"),
    path(
        "operations/retailers/new/",
        views.operations_seller_create,
        name="operations_seller_create",
    ),
    path(
        "operations/retailers/<int:pk>/",
        views.operations_seller_edit,
        name="operations_seller_edit",
    ),
    path("operations/products/", views.operations_products, name="operations_products"),
    path(
        "operations/products/new/",
        views.operations_product_create,
        name="operations_product_create",
    ),
    path(
        "operations/products/<int:pk>/",
        views.operations_product_edit,
        name="operations_product_edit",
    ),
    path(
        "operations/products/<int:pk>/variants/new/",
        views.operations_variant_create,
        name="operations_variant_create",
    ),
    path(
        "operations/variants/<int:pk>/",
        views.operations_variant_edit,
        name="operations_variant_edit",
    ),
    path(
        "operations/inventory/", views.operations_inventory, name="operations_inventory"
    ),
    path(
        "operations/inventory/<int:pk>/",
        views.operations_inventory_adjust,
        name="operations_inventory_adjust",
    ),
    path(
        "operations/categories/",
        views.operations_categories,
        name="operations_categories",
    ),
    path("operations/styles/", views.operations_styles, name="operations_styles"),
    path(
        "operations/customers/", views.operations_customers, name="operations_customers"
    ),
    path(
        "operations/customers/<int:pk>/",
        views.operations_customer_detail,
        name="operations_customer_detail",
    ),
    path("operations/orders/", views.operations_orders, name="operations_orders"),
    path(
        "operations/orders/<int:pk>/",
        views.operations_order_detail,
        name="operations_order_detail",
    ),
    path(
        "operations/commissions/",
        views.operations_commissions,
        name="operations_commissions",
    ),
    path("operations/model/", views.operations_model, name="operations_model"),
]
