document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#bulk-form");

  if (!form) {
    return;
  }

  const checks = form.querySelectorAll(".offer__check");
  const bar = form.querySelector(".bulk-bar");
  const selectAll = document.querySelector("#select-all");

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
    const anySelected = Array.from(checks).some((check) => check.checked);

    bar.classList.toggle("bulk-bar--disabled", !anySelected);

    bar.querySelectorAll("button").forEach((button) => {
      button.disabled = !anySelected;
    });

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
