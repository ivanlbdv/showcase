from django.urls import path

from .views import product_showcase

app_name = 'showcase'

urlpatterns = [
    path('', product_showcase, name='product_showcase'),
]
