document.querySelectorAll(".searchable-area-select").forEach((select) => {
  const choices = Array.from(select.options).map((option) => ({
    value: option.value,
    label: option.textContent,
  }));

  const wrapper = document.createElement("div");
  wrapper.className = "searchable-select";
  select.before(wrapper);
  wrapper.append(select);
  select.classList.add("native-select-hidden");

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "select-toggle";
  toggle.setAttribute("aria-haspopup", "listbox");
  toggle.setAttribute("aria-expanded", "false");

  const selectedLabel = document.createElement("span");
  const chevron = document.createElement("span");
  chevron.className = "select-chevron";
  chevron.textContent = "⌄";
  toggle.append(selectedLabel, chevron);

  const panel = document.createElement("div");
  panel.className = "select-panel";
  panel.hidden = true;

  const search = document.createElement("input");
  search.type = "search";
  search.className = "select-search";
  search.placeholder = select.dataset.searchPlaceholder || "Search";
  search.autocomplete = "off";
  search.setAttribute("aria-label", search.placeholder);

  const optionList = document.createElement("div");
  optionList.className = "select-options";
  optionList.setAttribute("role", "listbox");
  panel.append(search, optionList);
  wrapper.prepend(toggle, panel);

  function updateSelectedLabel() {
    const selected = choices.find((choice) => choice.value === select.value) || choices[0];
    selectedLabel.textContent = selected.label;
  }

  function closePanel() {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }

  function choose(choice) {
    select.value = choice.value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    updateSelectedLabel();
    closePanel();
  }

  function renderOptions(query = "") {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const matches = choices.filter((choice) =>
      choice.label.toLocaleLowerCase().includes(normalizedQuery)
    );
    optionList.replaceChildren();

    if (!matches.length) {
      const empty = document.createElement("p");
      empty.className = "select-empty";
      empty.textContent = select.dataset.noResults || "No matching areas";
      optionList.append(empty);
      return;
    }

    for (const choice of matches) {
      const optionButton = document.createElement("button");
      optionButton.type = "button";
      optionButton.className = "select-option";
      optionButton.textContent = choice.label;
      optionButton.setAttribute("role", "option");
      optionButton.setAttribute("aria-selected", String(choice.value === select.value));
      optionButton.addEventListener("click", () => choose(choice));
      optionList.append(optionButton);
    }
  }

  function openPanel() {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    search.value = "";
    renderOptions();
    search.focus();
  }

  toggle.addEventListener("click", () => panel.hidden ? openPanel() : closePanel());
  search.addEventListener("input", () => renderOptions(search.value));
  search.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePanel();
      toggle.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!wrapper.contains(event.target)) closePanel();
  });

  updateSelectedLabel();
});
