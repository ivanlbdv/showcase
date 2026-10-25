from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    class Category(models.TextChoices):
        SHORT_TERM = 'short_term', 'До 30 дней'
        LONG_TERM = 'long_term', 'Длительный срок'

    # Технические поля внешнего источника.
    # У существующих ручных карточек source будет "manual",
    # а external_id останется NULL.
    source = models.CharField(
        verbose_name="Источник",
        max_length=50,
        default="manual",
        editable=False,
    )

    external_id = models.CharField(
        verbose_name="ID внешн.",
        max_length=100,
        null=True,
        blank=True,
        editable=False,
    )

    external_modified_at = models.DateTimeField(
        verbose_name="Дата изменения у партнёра",
        null=True,
        blank=True,
        editable=False,
    )

    logo_url = models.URLField(
        verbose_name="URL логотипа",
        max_length=500,
        blank=True,
    )

    provider_name = models.CharField(
        verbose_name="Название МФО",
        max_length=120,
        help_text="Например: МФО «Пример».",
    )

    title = models.CharField(
        verbose_name="Название продукта",
        max_length=120,
        help_text="Например: До зарплаты.",
    )

    category = models.CharField(
        verbose_name="Категория по сроку",
        max_length=30,
        choices=Category.choices,
        default=Category.SHORT_TERM,
    )

    is_for_new_clients = models.BooleanField(
        verbose_name="Для новых клиентов",
        default=False,
        help_text="Карточка будет отображаться по фильтру «Новым клиентам».",
    )

    amount_text = models.CharField(
        verbose_name="Сумма",
        max_length=100,
        help_text="Например: от 1 000 до 30 000 ₽.",
    )

    term_text = models.CharField(
        verbose_name="Срок",
        max_length=100,
        help_text="Например: от 1 до 30 дней.",
    )

    rate_text = models.CharField(
        verbose_name="Ставка",
        max_length=100,
        help_text="Например: 0,8%.",
    )

    psk_text = models.CharField(
        verbose_name="ПСК",
        max_length=100,
        blank=True,
        help_text="Например: 281,00 – 292,00%.",
    )

    description = models.TextField(
        verbose_name="Краткое описание",
        blank=True,
        help_text="Текст будет показан в нижней части карточки.",
    )

    product_url = models.URLField(
        verbose_name="Ссылка на продукт",
        max_length=500,
        help_text="Полный URL страницы продукта или партнёрская ссылка.",
    )

    is_priority_offer = models.BooleanField(
        verbose_name="Приоритет",
        default=False,
        help_text=(
            "Приоритетные офферы показываются первыми "
            "и выделяются на витрине."
        ),
    )

    is_active = models.BooleanField(
        verbose_name="Показывать на витрине",
        default=True,
    )

    other_epc = models.DecimalField(
        verbose_name="EPC",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
        help_text="Доход на 100 кликов по данным Leads.su. Используется для сортировки витрины.",
    )

    legal_info = models.TextField(
        "Юридическая информация",
        blank=True,
        default="",
        help_text=(
            "Реквизиты МФО: наименование, адрес, ОГРН, ИНН, лицензия. "
            "Заполняется при синхронизации из группы «Лицензии»"
        ),
    )

    sort_order = models.PositiveIntegerField(
        verbose_name="Порядок показа",
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Чем меньше значение, тем выше карточка в витрине.",
    )

    created_at = models.DateTimeField(
        verbose_name="Дата добавления",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        verbose_name="Дата изменения",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Финансовое предложение"
        verbose_name_plural = "Финансовые предложения"
        ordering = ("sort_order", "-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "external_id"),
                condition=models.Q(external_id__isnull=False),
                name="unique_product_source_external_id",
            ),
        ]

    def __str__(self):
        return f"{self.provider_name} — {self.title}"
