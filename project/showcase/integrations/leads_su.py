import html as html_lib
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

# Ограничения fallback-парсинга условий из текста оффера.
DESCRIPTION_MAX_LENGTH = 200
MAX_AMOUNT = 10_000_000
MAX_TERM_DAYS = 1_000

# Законодательный максимум дневной ставки — 0,8% в день
# (эквивалент максимальной ПСК 292% годовых: 292 / 365 ≈ 0,8).
# Всё, что выше, — либо ПСК в годовых, либо штрафные проценты,
# либо ошибка партнёра. В дневную ставку такие значения не берём.
MAX_DAILY_RATE = Decimal("0.8")
MAX_PSK = Decimal("500")

# Дефолтная ПСК для карточек, у которых её не удалось извлечь.
# 292,00% — законодательный максимум ПСК (эквивалент 0,8% в день),
# поэтому значение не является фиктивным.
DEFAULT_PSK_TEXT = "0,00 – 292,00%"

# Дефолтная ставка для карточек, у которых ставку не удалось
# извлечь ни из extendedFields, ни из текста. Совпадает с
# законным максимумом дневной ставки (0,8% — это 292% годовых),
# поэтому не является фиктивным значением.
DEFAULT_RATE_TEXT = "от 0 до 0,8%"

# Блочные теги превращаем в переносы строк, чтобы пункты
# списков и абзацы не склеивались в один монолит — иначе
# fallback-парсинг не сможет найти условия по границам строк.
_BLOCK_TAG_RE = re.compile(
    r"(?i)<br\s*/?>|<hr\s*/?>"
    r"|</\s*(?:p|li|div|h[1-6]|ul|ol|tr)\s*>",
)


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
    psk_text: str
    other_epc: Decimal
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


def _parse_positive_int(value: Any, field_name: str) -> int:
    """
    Парсит значение в положительное целое число.
    Выбрасывает OfferValidationError при ошибке.
    """
    if value is None:
        raise OfferValidationError(f"Не заполнено обязательное поле «{field_name}».")

    text = _clean_text(value)

    if not text or text == "---":
        raise OfferValidationError(f"Поле «{field_name}» пустое или содержит заглушку.")

    try:
        result = int(text)
    except ValueError as exc:
        raise OfferValidationError(
            f"Поле «{field_name}» имеет неверный формат: ожидался int, получено «{text}»."
        ) from exc

    if result <= 0:
        raise OfferValidationError(
            f"Поле «{field_name}» должно быть положительным числом, получено {result}."
        )

    return result


def normalize_offer(
    offer: dict[str, Any],
    platform_id: str,
) -> NormalizedOffer:
    """
    Преобразует один оффер Leads.su в данные для Product.

    Условия (сумма, срок, ставка) берутся из extendedFields,
    если API их вернуло. Отсутствующие или пустые поля
    добираются fallback-парсингом из site_condition
    и description.

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

    # Эндпоинт возвращает только активные офферы (в запросе уже
    # передан status=active), поэтому поле status в payload может
    # отсутствовать. Отбрасываем только явно неактивные офферы.
    raw_status = _clean_text(offer.get("status")).casefold()
    if raw_status and raw_status != "active":
        raise OfferValidationError(
            "Оффер не имеет статуса active."
        )

    # Название МФО берём из site_name: там чистое название компании,
    # без служебных хвостов, которыми партнёры дополняют поле name
    # («Альфа Деньги для нерезидентов [micro][sale]» и т.п.).
    provider_name = _required_text(
        offer.get("site_name"),
        "site_name",
        max_length=120,
    )

    title = provider_name

    extended_fields = offer.get("extendedFields")
    structured = (
        extended_fields.get("Условия кредитования")
        if isinstance(extended_fields, dict)
        else None
    )

    full_description = _strip_html(offer.get("description"))

    # Текстовый fallback парсим всегда: он подстрахует
    # те поля, которые партнёр не заполнил в extendedFields.
    search_text = " ".join(
        (
            _clean_text(offer.get("site_condition")),
            full_description,
        )
    )

    parsed = _extract_terms_from_text(search_text)

    min_amount = _resolve_optional(
        structured,
        "Сумма кредита от",
        parsed,
        "min_amount",
    )
    max_amount = _resolve_required(
        structured,
        "Сумма кредита до",
        parsed,
        "max_amount",
        "Не найдена максимальная сумма займа "
        "ни в extendedFields, ни в тексте оффера.",
    )

    if min_amount is not None and min_amount > max_amount:
        raise OfferValidationError(
            "Минимальная сумма больше максимальной."
        )

    min_term_days = _resolve_optional(
        structured,
        "Срок кредитования от",
        parsed,
        "min_term_days",
    )
    max_term_days = _resolve_required(
        structured,
        "Срок кредитования до",
        parsed,
        "max_term_days",
        "Не найден максимальный срок кредитования "
        "ни в extendedFields, ни в тексте оффера.",
    )

    if min_term_days is not None and min_term_days > max_term_days:
        raise OfferValidationError(
            "Минимальный срок больше максимального."
        )

    if structured is not None:
        is_for_new_clients = _parse_yes_no(
            structured.get("Первый займ под 0%")
        )
    else:
        is_for_new_clients = parsed.get("for_new_clients", False)

    rate_text = _resolve_rate(structured, parsed)

    psk_text = _extract_psk(search_text) or DEFAULT_PSK_TEXT

    # Правило, согласованное для вашей витрины:
    # до 30 дней включительно — short_term,
    # более 30 дней — long_term.
    category = (
        Product.Category.LONG_TERM
        if max_term_days > 30
        else Product.Category.SHORT_TERM
    )

    if min_amount is not None and min_amount < max_amount:
        amount_text = (
            f"от {_format_number(min_amount)} "
            f"до {_format_number(max_amount)} ₽"
        )
    else:
        amount_text = f"до {_format_number(max_amount)} ₽"

    if min_term_days is not None and min_term_days < max_term_days:
        term_text = (
            f"от {min_term_days} "
            f"до {max_term_days} дней"
        )
    else:
        term_text = f"до {max_term_days} дней"

    # Описание на карточке не показывается, но сохраняем его
    # в усечённом виде для админки.
    description = _truncate_text(
        full_description.replace("\n", " "),
        DESCRIPTION_MAX_LENGTH,
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

    detail_stats = offer.get("detail_stats")
    system_stats = (
        detail_stats.get("system")
        if isinstance(detail_stats, dict)
        else None
    )

    other_epc = _parse_other_epc(
        system_stats.get("other_epc") if isinstance(system_stats, dict) else None,
    )

    return NormalizedOffer(
        external_id=external_id,
        provider_name=provider_name,
        title=title,
        category=category,
        is_for_new_clients=is_for_new_clients,
        amount_text=amount_text,
        term_text=term_text,
        # У API не указана единица измерения ставки.
        # Поэтому намеренно выводим только процент:
        # «0,8%», а не «0,8% в день».
        rate_text=rate_text,
        psk_text=psk_text,
        other_epc=other_epc,
        description=description,
        product_url=product_url,
        logo_url=logo_url,
        external_modified_at=external_modified_at,
        is_active=True,
    )


def _resolve_optional(
    structured: dict[str, Any] | None,
    structured_key: str,
    parsed: dict[str, Any],
    parsed_key: str,
) -> int | None:
    """
    Минимальные значения: берём из extendedFields или текста,
    а если их нет нигде — возвращаем None. Карточка тогда
    показывает просто «до X ₽» / «до X дней».
    """
    if structured is not None:
        try:
            return _parse_positive_int(
                structured.get(structured_key),
                structured_key,
            )
        except OfferValidationError:
            pass

    return parsed.get(parsed_key)


def _resolve_required(
    structured: dict[str, Any] | None,
    structured_key: str,
    parsed: dict[str, Any],
    parsed_key: str,
    error_message: str,
) -> int:
    """
    Максимальные значения: обязательны. Берём из extendedFields,
    если поле заполнено, иначе из fallback-парсинга,
    иначе ошибка — такую карточку не публикуем.
    """
    value = _resolve_optional(
        structured,
        structured_key,
        parsed,
        parsed_key,
    )

    if value is None:
        raise OfferValidationError(error_message)

    return value


def _resolve_rate(
    structured: dict[str, Any] | None,
    parsed: dict[str, Any],
) -> str:
    if structured is not None:
        try:
            return _format_rate(
                structured.get("Проценты по кредиту")
            )
        except OfferValidationError:
            pass

    rates = parsed.get("rates", [])

    if rates:
        return _format_parsed_rate(rates)

    return DEFAULT_RATE_TEXT


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

    # Нулевые символы приходят из Word-разметки партнёров
    # и не считаются пробелами для str.split().
    text = str(value).replace("\ufeff", "").replace("\u200b", "")

    return " ".join(text.split())


def _strip_html(value: Any) -> str:
    text = _clean_text(value)

    if not text or text.casefold() == "описание" or text == "---":
        return ""

    # Разрывы строк по блочным тегам: пункты списков и абзацы
    # не должны склеиваться в один монолит — иначе fallback-парсинг
    # не сможет найти условия по границам строк.
    text = _BLOCK_TAG_RE.sub("\n", text)

    # Партнёры присылают и настоящий HTML (<p>...</p>),
    # и экранированный (&lt;p&gt;...&lt;/p&gt;).
    # Чистим в цикле: раскодировали -> срезали теги -> снова раскодировали.
    for _ in range(3):
        decoded = html_lib.unescape(text)
        stripped = strip_tags(decoded)

        if stripped == text:
            break

        text = stripped

    # Нормализуем пробелы внутри строк и убираем пустые.
    lines = [" ".join(line.split()) for line in text.splitlines()]

    return "\n".join(line for line in lines if line)


def _truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text

    # Обрезаем по границе слова, чтобы не оставлять обрубок.
    cut = text[:max_length].rsplit(" ", 1)[0].rstrip(" ,.;:—-…")

    return f"{cut}…"


def _digits_to_int(text: str) -> int | None:
    digits = re.sub(r"\D", "", text)

    return int(digits) if digits else None


def _extract_amount(text: str) -> tuple[int | None, int | None]:
    """
    Собирает ВСЕ кандидаты сумм по всему тексту:
    min = минимум из найденных «от X», max = максимум из «до Y».
    """
    lows: list[int] = []
    highs: list[int] = []

    for m in re.finditer(
        r"от\s*([\d\s\u00a0]{1,12})\s*(?:до|—|–|-)\s*"
        r"([\d\s\u00a0]{1,12})\s*(?:руб|₽)",
        text,
        re.IGNORECASE,
    ):
        low, high = _digits_to_int(m.group(1)), _digits_to_int(m.group(2))
        if low and high and 0 < low <= high <= MAX_AMOUNT:
            lows.append(low)
            highs.append(high)

    if not highs:
        for m in re.finditer(
            r"(?:сумм\w*(?:\s+за[йё]м\w*)?|за[йё]м|лимит\w*)"
            r"[^.\n]{0,15}?до\s*([\d\s\u00a0]{1,12})\s*(?:руб|₽)",
            text,
            re.IGNORECASE,
        ):
            high = _digits_to_int(m.group(1))
            if high and 0 < high <= MAX_AMOUNT:
                highs.append(high)

    if not highs:
        for m in re.finditer(
            r"максимальн\w*\s+сумм\w+[^.\n]{0,15}?"
            r"([\d\s\u00a0]{1,12})\s*руб",
            text,
            re.IGNORECASE,
        ):
            high = _digits_to_int(m.group(1))
            if high and 0 < high <= MAX_AMOUNT:
                highs.append(high)

    if not highs:
        return None, None

    low = min(lows) if lows else None
    high = max(highs)

    if low is not None and low >= high:
        low = None

    return low, high


def _extract_term_days(text: str) -> tuple[int | None, int | None]:
    """
    Собирает ВСЕ кандидаты сроков по всему тексту:
    min = минимум из «от X», max = максимум из «до Y» (дни/недели).
    """
    lows: list[int] = []
    highs: list[int] = []

    for m in re.finditer(
        r"от\s*(\d+)\s*(?:дн\w*)?\s*(?:до|—|–|-)\s*(\d+)\s*(дн\w*|недел\w*)",
        text,
        re.IGNORECASE,
    ):
        low, high = int(m.group(1)), int(m.group(2))
        if "недел" in m.group(3).casefold():
            low, high = low * 7, high * 7
        if 0 < low <= high <= MAX_TERM_DAYS:
            lows.append(low)
            highs.append(high)

    if not highs:
        for m in re.finditer(
            r"(?:срок|лимит)[^.\n]{0,40}?до\s*(\d+)\s*(дн\w*|недел\w*)",
            text,
            re.IGNORECASE,
        ):
            high = int(m.group(1))
            if "недел" in m.group(2).casefold():
                high *= 7
            if 0 < high <= MAX_TERM_DAYS:
                highs.append(high)

    if not highs:
        for m in re.finditer(
            r"максимальн\w*\s+срок\w*[^.\n]{0,15}?(\d+)\s*дн",
            text,
            re.IGNORECASE,
        ):
            high = int(m.group(1))
            if 0 < high <= MAX_TERM_DAYS:
                highs.append(high)

    if not highs:
        return None, None

    low = min(lows) if lows else None
    high = max(highs)

    if low is not None and low >= high:
        low = None

    return low, high


def _extract_rates(text: str) -> list[Decimal]:
    """
    Собирает все дневные ставки (≤ 0,8%) по всему тексту.
    ПСК (сотни процентов) и штрафные проценты отсекаются фильтром.
    """
    rates: list[Decimal] = []

    for raw in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", text):
        try:
            value = Decimal(raw.replace(",", "."))
        except InvalidOperation:
            continue

        if value <= MAX_DAILY_RATE:
            rates.append(value)

    return rates


def _has_zero_rate_for_new_clients(text: str) -> bool:
    return bool(
        re.search(r"под\s*0\s*%", text, re.IGNORECASE)
        or re.search(
            r"перв[ыи][йм][ао]?\s+за[йё]м[^.\n]{0,40}?0\s*%",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"перв[ыи][йм][ао]?\s+за[йё]м\s+бесплатно",
            text,
            re.IGNORECASE,
        )
    )


def _extract_terms_from_text(text: str) -> dict[str, Any]:
    """
    Извлекает сумму, срок, ставку и признак «под 0%»
    из свободного текста оффера. Это best-effort: партнёры
    пишут тексты вольно, поэтому отсутствующие значения
    просто не попадают в результат.
    """
    result: dict[str, Any] = {}

    min_amount, max_amount = _extract_amount(text)

    if max_amount is not None:
        result["max_amount"] = max_amount
    if min_amount is not None:
        result["min_amount"] = min_amount

    min_term_days, max_term_days = _extract_term_days(text)

    if max_term_days is not None:
        result["max_term_days"] = max_term_days
    if min_term_days is not None:
        result["min_term_days"] = min_term_days

    rates = _extract_rates(text)

    if rates:
        result["rates"] = rates

    result["for_new_clients"] = _has_zero_rate_for_new_clients(text)

    return result


def _format_rate_value(value: Decimal) -> str:
    formatted = format(value.normalize(), "f")

    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")

    return formatted.replace(".", ",")


def _format_psk_value(value: Decimal) -> str:
    # Формат по требованиям к рекламе: два знака после запятой,
    # например «292,00».
    return f"{value:.2f}".replace(".", ",")


def _extract_psk(text: str) -> str:
    """
    Ищет полную стоимость кредита (ПСК) в тексте оффера.

    Форматы: «ПСК 286,400% - 292,000%», «ПСК 0–292% годовых»,
    «ПСК от 255,5% до 292% годовых».
    """
    match = re.search(
        r"ПСК[^.\n]{0,50}?(\d+(?:[.,]\d+)?)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return ""

    segment = text[match.start():match.start() + 100]
    values: list[Decimal] = []

    for raw in re.findall(r"(\d+(?:[.,]\d+)?)", segment):
        try:
            value = Decimal(raw.replace(",", "."))
        except InvalidOperation:
            continue

        if value <= MAX_PSK:
            values.append(value)

    if not values:
        return ""

    low = min(values)
    high = max(values)

    if low < high:
        return f"{_format_psk_value(low)} – {_format_psk_value(high)}%"

    return f"{_format_psk_value(high)}%"


def _format_parsed_rate(rates: list[Decimal]) -> str:
    # Вызывается только с непустым списком (см. _resolve_rate),
    # поэтому проверка на пустоту здесь не нужна.
    low = min(rates)
    high = max(rates)

    if low < high:
        return (
            f"от {_format_rate_value(low)} "
            f"до {_format_rate_value(high)}%"
        )

    return f"{_format_rate_value(high)}%"


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

    # Дневная ставка выше 0,8% невозможна по закону: значение
    # либо указано в других единицах, либо ошибочно. Считаем
    # поле невалидным — _resolve_rate уйдёт в текст или дефолт.
    if rate > MAX_DAILY_RATE:
        raise OfferValidationError(
            "Поле «Проценты по кредиту» превышает законный максимум "
            "дневной ставки."
        )

    return f"{_format_rate_value(rate)}%"


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
    """
    Логотип необязателен: битый или слишком длинный URL
    не должен отклонять весь оффер — пишем предупреждение
    в лог и возвращаем пустую строку.
    """
    text = _clean_text(value)

    if not text:
        return ""

    if len(text) > 500:
        logger.warning(
            "Поле «%s» длиннее 500 символов — логотип не сохранён.",
            field_name,
        )

        return ""

    if not _is_valid_https_url(text):
        logger.warning(
            "Поле «%s» содержит некорректный HTTPS URL: %r",
            field_name,
            text[:200],
        )

        return ""

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

    # Дата изменения — служебное поле: неизвестный формат
    # не повод отклонять карточку.
    logger.warning(
        "Поле modified имеет неизвестный формат: %r",
        text[:100],
    )

    return None


def _parse_other_epc(value: Any) -> Decimal:
    """
    Извлекает other_epc из detail_stats.system.
    Значение может отсутствовать, быть null или строкой —
    в любом проблемном случае считаем его нулём: карточку
    статистика не должна отклонять.
    """
    if not isinstance(value, (str, int, float)):
        return Decimal("0.00")

    text = str(value).strip()

    if not text:
        return Decimal("0.00")

    try:
        epc = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return Decimal("0.00")

    if epc < 0:
        return Decimal("0.00")

    return epc


def _format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")
