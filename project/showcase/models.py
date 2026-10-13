from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    class Category(models.TextChoices):
        SHORT_TERM = "short_term", "До 30 дней"
        LONG_TERM = "long_term", "Длительный срок"

    provider_name = models.CharField(
        verbose_name="Название МФО / банка",
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
        verbose_name="Предложение для новых клиентов",
        default=False,
        help_text="Карточка будет отображаться по фильтру «Новым клиентам».",
    )

    amount_text = models.CharField(
        verbose_name="Сумма",
        max_length=100,
        help_text="Например: до 30 000 ₽.",
    )

    term_text = models.CharField(
        verbose_name="Срок",
        max_length=100,
        help_text="Например: до 30 дней.",
    )

    rate_text = models.CharField(
        verbose_name="Ставка",
        max_length=100,
        help_text="Например: от 0% в день.",
    )

    feature_label = models.CharField(
        verbose_name="Название дополнительного параметра",
        max_length=100,
        default="Решение",
        help_text="Например: Решение, Получение, Документы.",
    )

    feature_value = models.CharField(
        verbose_name="Значение дополнительного параметра",
        max_length=100,
        help_text="Например: за 5 минут.",
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

    is_active = models.BooleanField(
        verbose_name="Показывать на витрине",
        default=True,
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
        verbose_name = "Банковский продукт"
        verbose_name_plural = "Банковские продукты"
        ordering = ("sort_order", "-created_at")

    def __str__(self):
        return f"{self.provider_name} — {self.title}"
