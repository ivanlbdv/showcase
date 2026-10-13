document.addEventListener("DOMContentLoaded", () => {
  const filters = document.querySelectorAll(".filter");
  const cards = document.querySelectorAll(".card");

  filters.forEach((filter) => {
    filter.addEventListener("click", () => {
      const selectedFilter = filter.dataset.filter;

      filters.forEach((item) => {
        const isSelected = item === filter;

        item.classList.toggle("is-active", isSelected);
        item.setAttribute("aria-pressed", String(isSelected));
      });

      cards.forEach((card) => {
        const categories = card.dataset.categories.split(" ");

        const shouldShow =
          selectedFilter === "all" ||
          categories.includes(selectedFilter);

        card.hidden = !shouldShow;
      });
    });
  });
});