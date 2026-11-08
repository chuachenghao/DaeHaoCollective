from django.conf import settings


def navigation(request):
    bag_count = 0
    if request.user.is_authenticated and request.user.role == "CUSTOMER":
        from .models import CartItem

        items = CartItem.objects.filter(cart__customer__account=request.user)
        for item in items:
            bag_count += item.quantity
    return {"bag_count": bag_count, "site_name": settings.SITE_NAME}
