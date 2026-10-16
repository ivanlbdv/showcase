from django.conf import settings
from django.shortcuts import render


class MaintenanceModeMiddleware:
    """
    При включенном MAINTENANCE_MODE возвращает страницу 503
    для всех входящих запрсов, кроме запросов разработчика.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'MAINTENANCE_MODE', False):
            return self.get_response(request)

        client_ip = self.get_client_ip(request)

        allowed_ips = getattr(
            settings,
            'MAINTENANCE_ALLOWED_IPS',
            [],
        )

        if client_ip in allowed_ips:
            return self.get_response(request)

        response = render(
            request,
            'errors/503.html',
            status=503,
        )

        response['Retry-After'] = '3600'

        return response

    @staticmethod
    def get_client_ip(request):
        return request.META.get('REMOTE_ADDR')
