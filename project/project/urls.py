"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('', include('showcase.urls')),
]

admin_prefix = os.environ.get('DJANGO_ADMIN_URL', '')

if admin_prefix:
    urlpatterns.append(
        path(f'{admin_prefix}/', admin.site.urls),
    )
print(urlpatterns)

handler400 = 'showcase.error_views.error_400'
handler403 = 'showcase.error_views.error_403'
handler404 = 'showcase.error_views.error_404'
handler500 = 'showcase.error_views.error_500'
