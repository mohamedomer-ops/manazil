(() => {
  const field = document.querySelector('.home-search-transaction');
  if (!field) return;

  const select = field.querySelector('select[name="transaction"]');
  const buttons = Array.from(field.querySelectorAll('[data-transaction]'));
  if (!select || buttons.length !== 2) return;

  const update = (value) => {
    select.value = value;
    buttons.forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.transaction === value));
    });
  };
  buttons.forEach((button) => button.addEventListener('click', () => update(button.dataset.transaction)));
  select.addEventListener('change', () => update(select.value));
  update(select.value);
  field.classList.add('home-search-enhanced');
})();
