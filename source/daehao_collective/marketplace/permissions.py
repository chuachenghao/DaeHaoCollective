from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def check_access(request, allowed_roles, approved_seller=False):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if request.user.role not in allowed_roles:
        raise PermissionDenied
    if approved_seller:
        if not hasattr(request.user, "seller") or not request.user.seller.can_trade():
            return redirect("seller_status")
    return None
