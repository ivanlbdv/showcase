import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from django.utils import timezone
from django.utils.html import strip_tags
from showcase.models import Product

logger = logging.getLogger(__name__)


class LeadsSuAPIError(Exception):
    """Ошибка ответа или соединения с API Leads.su."""


class OfferValidationError(Exception):
    """Оффер не подходит для автоматической публикации."""


@dataclass(frozen=True)
class NormalizedOffer:
    external_id: str
    provider_name: str
    title: str
    category: str
    is_for_new_clients: bool
    amount_text: str
    term_text: str
    rate_text: str
    feature_label: str
    feature_value: str
    description: str
    product_url: str
    logo_url: str
    external_modified_at: datetime | None
    is_active: bool


class LeadsSuClient:
    BASE_URL = (
        "https://api.leads.su/"
        "webmaster/offers/connectedPlatforms"
    )

    PAGE_SIZE = 500
    MAX_RETRIES = 3

    def __init__(self, api_token: str, platform_id: str):
        self.api_token = api_token.strip()
        self.platform_id = str(platform_id).strip()
        self.session = requests.Session()

    def fetch_all_active_offers(self) -> list[dict[str, Any]]:
        """
        Загружает все активные офферы площадки.

        Исключение выбрасывается при любой ошибке API. В таком случае
        management command не будет массово деактивировать карточки.
        """
        if not self.api_token:
            raise LeadsSuAPIError(
                "Не задана переменная окружения LEADS_API_TOKEN."
            )

        if not self.platform_id:
            raise LeadsSuAPIError(
                "Не задана переменная окружения LEADS_PLATFORM_ID."
            )

        offers: list[dict[str, Any]] = []
        offset = 0
        expected_count: int | None = None

        while True:
            payload = self._request_page(offset=offset)

            data = payload.get("data")
            if not isinstance(data, list):
                raise LeadsSuAPIError(
                    "API Leads.su вернуло некорректное поле data."
                )

            current_count = self._parse_non_negative_int(
                payload.get("count"),
                field_name="count",
            )

            if expected_count is None:
                expected_count = current_count
            elif current_count != expected_count:
                raise LeadsSuAPIError(
                    "Количество офферов изменилось во время синхронизации. "
                    "Повторите запуск позже."
                )

            offers.extend(data)

            if len(offers) >= expected_count:
                return offers[:expected_count]

            if not data:
                raise LeadsSuAPIError(
                    "API вернуло пустую страницу до получения "
                    "всех заявленных офферов."
                )

            new_offset = offset + len(data)

            if new_offset <= offset:
                raise LeadsSuAPIError(
                    "API вернуло некорректную пагинацию."
                )

            offset = new_offset

    def _request_page(self, offset: int) -> dict[str, Any]:
        params = {
            "token": self.api_token,
            "platform_id": self.platform_id,
            "status": "active",
            "offset": offset,
            "limit": self.PAGE_SIZE,
            "geo": 1,
            "extendedFields": 1,
            "response_type": "Json",
        }

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=(5, 30),
                )

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == self.MAX_RETRIES:
                        response.raise_for_status()

                    self._sleep_before_retry(response, attempt)
                    continue

                response.raise_for_status()

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise LeadsSuAPIError(
                        "API Leads.su вернуло некорректный JSON."
                    ) from exc

                if not isinstance(payload, dict):
                    raise LeadsSuAPIError(
                        "API Leads.su вернуло JSON неверного формата."
                    )

                if (
                    payload.get("status") != "success"
                    or payload.get("code") != 200
                ):
                    raise LeadsSuAPIError(
                        "API Leads.su сообщило об ошибке: "
                        f"{payload.get('error', payload.get('error_msg', 'unknown error'))}"
                    )

                return payload

            except requests.RequestException as exc:
                if attempt == self.MAX_RETRIES:
                    raise LeadsSuAPIError(
                        "Не удалось выполнить запрос к API Leads.su."
                    ) from exc

                self._sleep_before_retry(None, attempt)

        raise LeadsSuAPIError(
            "Не удалось получить ответ от API Leads.su."
        )

    @staticmethod
    def _sleep_before_retry(
        response: requests.Response | None,
        attempt: int,
    ) -> None:
        retry_after = None

        if response is not None:
            retry_after = response.headers.get("Retry-After")

        try:
            delay = min(int(retry_after), 60) if retry_after else 2**attempt
        except ValueError:
            delay = 2**attempt

        time.sleep(delay)

    @staticmethod
    def _parse_non_negative_int(value: Any, field_name: str) -> int:
        try:
            result = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise LeadsSuAPIError(
                f"API вернуло некорректное значение {field_name}."
            ) from exc

        if result < 0:
            raise LeadsSuAPIError(
                f"API вернуло отрицательное значение {field_name}."
            )

        return result


def normalize_offer(
    offer: dict[str, Any],
    platform_id: str,
) -> NormalizedOffer:
    """
    Преобразует один оффер Leads.su в данные для Product.

    В случае недостатка обязательных данных выбрасывает
    OfferValidationError. Такая карточка не создаётся/не обновляется.
    """
    if not isinstance(offer, dict):
        raise OfferValidationError("Оффер имеет неверный формат.")

    external_id = _required_text(
        offer.get("id"),
        "id",
        max_length=100,
    )

    status = _required_text(
        offer.get("status"),
        "status",
        max_length=30,
    ).lower()

    if status != "active":
        raise OfferValidationError(
            "Оффер не имеет статуса active."
        )

    provider_name = _required_text(
        offer.get("site_name"),
        "site_name",
        max_length=120,
    )

    title = _clean_offer_name(
        _required_text(
            offer.get("name"),
            "name",
            max_length=300,
        )
    )

    if not title:
        raise OfferValidationError(
            "После очистки name название оффера оказалось пустым."
        )

    if len(title) > 120:
        raise OfferValidationError(
            "Название оффера длиннее 120 символов."
        )

    extended_fields = offer.get("extendedFields")

    if not isinstance(extended_fields, dict):
        raise OfferValidationError(
            "Не найден объект extendedFields."
        )

    credit_terms = extended_fields.get("Условия кредитования")

    if not isinstance(credit_terms, dict):
        raise OfferValidationError(
            "Не найден раздел «Условия кредитования»."
        )

    min_amount = _parse_positive_int(
        credit_terms.get("Сумма кредита от"),
        "Сумма кредита от",
    )
    max_amount = _parse_positive_int(
        credit_terms.get("Сумма кредита до"),
        "Сумма кредита до",
    )

    if min_amount > max_amount:
        raise OfferValidationError(
            "Минимальная сумма больше максимальной."
        )

    min_term_days = _parse_positive_int(
        credit_terms.get("Срок кредитования от"),
        "Срок кредитования от",
    )
    max_term_days = _parse_positive_int(
        credit_terms.get("Срок кредитования до"),
        "Срок кредитования до",
    )

    if min_term_days > max_term_days:
        raise OfferValidationError(
            "Минимальный срок больше максимального."
        )

    # Правило, согласованное для вашей витрины:
    # до 30 дней включительно — short_term,
    # более 30 дней — long_term.
    category = (
        Product.Category.LONG_TERM
        if max_term_days > 30
        else Product.Category.SHORT_TERM
    )

    is_for_new_clients = _parse_yes_no(
        credit_terms.get("Первый займ под 0%"),
    )

    rate_text = _format_rate(
        credit_terms.get("Проценты по кредиту")
    )

    feature_label, feature_value = _get_feature(
        credit_terms
    )

    description = _clean_description(
        offer.get("description")
    )

    product_url = _select_tracking_url(
        offer.get("tracking_urls"),
        platform_id,
    )

    logo_url = _optional_https_url(
        offer.get("logo"),
        "logo",
    )

    external_modified_at = _parse_partner_date(
        offer.get("modified")
    )

    return NormalizedOffer(
        external_id=external_id,
        provider_name=provider_name,
        title=title,
        category=category,
        is_for_new_clients=is_for_new_clients,
        amount_text=(
            f"от {_format_number(min_amount)} "
            f"до {_format_number(max_amount)} ₽"
        ),
        term_text=(
            f"от {min_term_days} "
            f"до {max_term_days} дней"
        ),
        # У API не указана единица измерения ставки.
        # Поэтому намеренно выводим только процент:
        # «0,8%», а не «0,8% в день».
        rate_text=rate_text,
        feature_label=feature_label,
        feature_value=feature_value,
        description=description,
        product_url=product_url,
        logo_url=logo_url,
        external_modified_at=external_modified_at,
        is_active=True,
    )


def _required_text(
    value: Any,
    field_name: str,
    max_length: int,
) -> str:
    text = _clean_text(value)

    if not text or text == "---":
        raise OfferValidationError(
            f"Не заполнено обязательное поле «{field_name}»."
        )

    if len(text) > max_length:
        raise OfferValidationError(
            f"Поле «{field_name}» длиннее {max_length} символов."
        )

    return text


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).split())


def _clean_offer_name(value: str) -> str:
    """
    Удаляет один или несколько служебных хвостов:
    «Vivus.ru [micro][sale]» -> «Vivus.ru».
    """
    return re.sub(
        r"(?:\s*&{: [^ :}&]+\])+\s*$",
        "",
        value,
    ).strip()


def _clean_description(value: Any) -> str:
    text = _clean_text(value)

    if not text or text.casefold() == "описание" or text == "---":
        return ""

    # Если партнёр прислал HTML, он превращается в обычный текст.
    # Это предотвращает отображение HTML-разметки как текста.
    return " ".join(strip_tags(text).split())


def _parse_positive_int(value: Any, field_name: str) -> int:
    text = _clean_text(value)

    if not text or text == "---":
        raise OfferValidationError(
            f"Не заполнено поле «{field_name}»."
        )

    normalized = re.sub(r"[^\d]", "", text)

    try:
        result = int(normalized)
    except ValueError as exc:
        raise OfferValidationError(
            f"Поле «{field_name}» не является целым числом."
        ) from exc

    if result <= 0:
        raise OfferValidationError(
            f"Поле «{field_name}» должно быть больше нуля."
        )

    return result


def _parse_yes_no(value: Any) -> bool:
    return _clean_text(value).casefold() in {
        "да",
        "yes",
        "true",
        "1",
    }


def _format_rate(value: Any) -> str:
    text = _clean_text(value)

    if not text or text == "---":
        raise OfferValidationError(
            "Не заполнено поле «Проценты по кредиту»."
        )

    normalized = text.replace(",", ".")

    try:
        rate = Decimal(normalized)
    except InvalidOperation as exc:
        raise OfferValidationError(
            "Поле «Проценты по кредиту» имеет неверный формат."
        ) from exc

    if rate < 0:
        raise OfferValidationError(
            "Процентная ставка не может быть отрицательной."
        )

    formatted = format(rate.normalize(), "f")

    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")

    return f"{formatted.replace('.', ',')}%"


def _get_feature(
    credit_terms: dict[str, Any],
) -> tuple[str, str]:
    advantage = _clean_text(
        credit_terms.get("Преимущество")
    )

    if advantage and advantage != "---":
        if len(advantage) > 100:
            raise OfferValidationError(
                "Значение «Преимущество» длиннее 100 символов."
            )

        return "Преимущество", advantage

    receiving_method = _clean_text(
        credit_terms.get("Способ получения кредита")
    )

    if receiving_method and receiving_method != "---":
        if len(receiving_method) > 100:
            raise OfferValidationError(
                "Значение «Способ получения кредита» длиннее 100 символов."
            )

        return "Получение", receiving_method

    raise OfferValidationError(
        "Не заполнены «Преимущество» и "
        "«Способ получения кредита»."
    )


def _select_tracking_url(
    tracking_urls: Any,
    platform_id: str,
) -> str:
    if not isinstance(tracking_urls, list):
        raise OfferValidationError(
            "Не найден список tracking_urls."
        )

    selected_urls: list[str] | None = None

    for item in tracking_urls:
        if not isinstance(item, dict):
            continue

        if str(item.get("platform_id")) != str(platform_id):
            continue

        urls = item.get("urls")

        if isinstance(urls, list):
            selected_urls = [
                _clean_text(url)
                for url in urls
                if _clean_text(url)
            ]
            break

    if not selected_urls:
        raise OfferValidationError(
            "Не найдены tracking URL для текущей площадки."
        )

    https_urls = [
        url
        for url in selected_urls
        if _is_valid_https_url(url)
    ]

    if not https_urls:
        raise OfferValidationError(
            "Для площадки нет корректного HTTPS tracking URL."
        )

    # Предпочитаем default landing — URL без url_id.
    for url in https_urls:
        query = parse_qs(urlparse(url).query)

        if "url_id" not in query:
            return url

    # Если default landing отсутствует, используем первую HTTPS-ссылку.
    return https_urls[0]


def _optional_https_url(
    value: Any,
    field_name: str,
) -> str:
    text = _clean_text(value)

    if not text:
        return ""

    if len(text) > 500:
        raise OfferValidationError(
            f"Поле «{field_name}» длиннее 500 символов."
        )

    if not _is_valid_https_url(text):
        raise OfferValidationError(
            f"Поле «{field_name}» содержит некорректный HTTPS URL."
        )

    return text


def _is_valid_https_url(value: str) -> bool:
    parsed = urlparse(value)

    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
    )


def _parse_partner_date(value: Any) -> datetime | None:
    text = _clean_text(value)

    if not text:
        return None

    for date_format in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            naive_datetime = datetime.strptime(
                text,
                date_format,
            )

            return timezone.make_aware(
                naive_datetime,
                timezone.get_current_timezone(),
            )
        except ValueError:
            continue

    raise OfferValidationError(
        "Поле modified имеет неизвестный формат даты."
    )


def _format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")
