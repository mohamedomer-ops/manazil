document.querySelectorAll('[data-auth-phone]').forEach((row) => {
  const country = row.querySelector('select[name="country_code"]');
  const number = row.querySelector('input[name="phone_number"]');
  const flag = row.querySelector('[data-country-flag]');
  const code = row.querySelector('[data-country-code]');
  if (!country || !number || !flag || !code) return;
  const updateCountry = () => {
    const selected = country.selectedOptions[0];
    if (!selected) return;
    number.placeholder = selected.dataset.example || '912345678';
    flag.textContent = selected.dataset.flag;
    code.textContent = selected.value;
    country.setAttribute('aria-label', `${country.dataset.label}, ${selected.dataset.country} ${selected.value}`);
  };
  country.addEventListener('change', updateCountry);
  updateCountry();
});
