document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#bulk-form");

  if (!form) {
    return;
  }

  const checks = Array.from(
    form.querySelectorAll(".offer__check"),
  );
  const offers = Array.from(
    form.querySelectorAll(".offer"),
  );
  const bar = form.querySelector(".bulk-bar");
  const selectAll = document.querySelector("#select-all");
  const filters = Array.from(
    document.querySelectorAll(".filter[data-filter]"),
  );
  const filterEmpty = document.querySelector("#filter-empty");
  const offersContainer = form.querySelector(".offers");
  const sortSelect = document.querySelector("#offer-sort");

  const originalOrder = new Map(
    offers.map((offer, index) => [offer, index]),
  );

  const sortOffers = () => {
    if (!offersContainer || !sortSelect) {
      return;
    }

    const sortType = sortSelect.value;
    const sortedOffers = [...offers];

    sortedOffers.sort((a, b) => {
      if (sortType === "default") {
        return originalOrder.get(a) - originalOrder.get(b);
      }

      if (sortType === "name-asc" || sortType === "name-desc") {
        const result = (a.dataset.sortName || "").localeCompare(
          b.dataset.sortName || "",
          "ru",
          { sensitivity: "base" },
        );

        return sortType === "name-asc" ? result : -result;
      }

      if (sortType === "epc-asc" || sortType === "epc-desc") {
        const epcA = Number.parseFloat(
          (a.dataset.sortEpc || "0").replace(",", "."),
        ) || 0;

        const epcB = Number.parseFloat(
          (b.dataset.sortEpc || "0").replace(",", "."),
        ) || 0;

        return sortType === "epc-asc"
          ? epcA - epcB
          : epcB - epcA;
      }

      return 0;
    });

    sortedOffers.forEach((offer) => {
      offersContainer.appendChild(offer);
    });
  };

  if (sortSelect) {
    sortSelect.addEventListener("change", sortOffers);
  }

  let currentFilter = "all";

  const visibleChecks = () =>
    checks.filter((check) => {
      const offer = check.closest(".offer");

      return offer && !offer.hidden;
    });

  const updateSelectAll = () => {
    if (!selectAll) {
      return;
    }

    const currentChecks = visibleChecks();
    const checkedCount = currentChecks.filter(
      (check) => check.checked,
    ).length;

    selectAll.checked =
      currentChecks.length > 0 &&
      checkedCount === currentChecks.length;

    selectAll.indeterminate =
      checkedCount > 0 &&
      checkedCount < currentChecks.length;
  };

  const updateBar = () => {
    const anySelected = checks.some(
      (check) => check.checked,
    );

    if (bar) {
      bar.classList.toggle(
        "bulk-bar--disabled",
        !anySelected,
      );

      bar.querySelectorAll("button").forEach((button) => {
        button.disabled = !anySelected;
      });
    }

    updateSelectAll();
  };

  const matchesFilter = (offer) => {
    if (currentFilter === "active") {
      return offer.dataset.showcase === "true";
    }

    if (currentFilter === "priority") {
      return offer.dataset.priority === "true";
    }

    if (currentFilter === "hidden") {
      return offer.dataset.active === "false";
    }

    return true;
  };

  const applyFilter = () => {
    let visibleCount = 0;

    offers.forEach((offer) => {
      const shouldShow = matchesFilter(offer);

      offer.hidden = !shouldShow;

      if (shouldShow) {
        visibleCount += 1;
      }
    });

    filters.forEach((filter) => {
      const isSelected =
        filter.dataset.filter === currentFilter;

      filter.classList.toggle(
        "is-active",
        isSelected,
      );

      filter.setAttribute(
        "aria-pressed",
        String(isSelected),
      );
    });

    if (filterEmpty) {
      filterEmpty.hidden =
        offers.length === 0 || visibleCount > 0;
    }

    updateSelectAll();
  };

  filters.forEach((filter) => {
    filter.addEventListener("click", () => {
      currentFilter = filter.dataset.filter || "all";
      applyFilter();
    });
  });

  checks.forEach((check) => {
    check.addEventListener("change", updateBar);
  });

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      visibleChecks().forEach((check) => {
        check.checked = selectAll.checked;
      });

      updateBar();
    });
  }

  applyFilter();
  updateBar();
});
