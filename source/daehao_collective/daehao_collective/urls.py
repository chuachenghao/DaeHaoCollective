from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from marketplace import views

urlpatterns = [
    path('', include('marketplace.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [re_path(r'^.*$', views.page_not_found)]

handler403 = 'marketplace.views.permission_denied'
handler404 = 'marketplace.views.page_not_found'
handler500 = 'marketplace.views.server_error'
