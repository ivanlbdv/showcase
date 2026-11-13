import os


class NoIndexPrivatePagesMiddleware:
    """
    Запрещает индексацию личного кабинета
    и административной панели.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path

        admin_prefix = os.environ.get(
            "DJANGO_ADMIN_URL", ""
        ).strip("/")

        is_dashboard = (
            path == "/lk"
            or path.startswith("/lk/")
        )

        is_admin = bool(admin_prefix) and (
            path == f"/{admin_prefix}"
            or path.startswith(f"/{admin_prefix}/")
        )

        if is_dashboard or is_admin:
            response["X-Robots-Tag"] = (
                "noindex, nofollow, noarchive"
            )

        return response
