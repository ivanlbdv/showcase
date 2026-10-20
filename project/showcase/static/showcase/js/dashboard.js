document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#bulk-form");

  if (!form) {
    return;
  }

  const checks = form.querySelectorAll(".offer__check");
  const bar = form.querySelector(".bulk-bar");
  const selectAll = document.querySelector("#select-all");

  const hideButton = bar.querySelector('button[value="hide"]');
  const showButton = bar.querySelector('button[value="show"]');

  const updateSelectAll = () => {
    if (!selectAll) {
      return;
    }

    const checkedCount = Array.from(checks).filter(
      (check) => check.checked,
    ).length;

    selectAll.checked = checks.length > 0 && checkedCount === checks.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < checks.length;
  };

  const updateBar = () => {
    const selected = Array.from(checks).filter((check) => check.checked);

    const anySelected = selected.length > 0;
    const hasActive = selected.some(
      (check) => check.dataset.state === "active",
    );
    const hasHidden = selected.some(
      (check) => check.dataset.state === "hidden",
    );

    bar.classList.toggle("bulk-bar--disabled", !anySelected);

    bar.querySelectorAll("button").forEach((button) => {
      button.disabled = !anySelected;
    });

    if (hideButton && anySelected) {
      hideButton.disabled = !hasActive;
    }

    if (showButton && anySelected) {
      showButton.disabled = !hasHidden;
    }

    updateSelectAll();
  };

  checks.forEach((check) => {
    check.addEventListener("change", updateBar);
  });

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      checks.forEach((check) => {
        check.checked = selectAll.checked;
      });

      updateBar();
    });
  }

  updateBar();
});
