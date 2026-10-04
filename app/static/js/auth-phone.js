document.querySelectorAll('[data-auth-phone]').forEach((row) => {
  const country = row.querySelector('select[name="country_code"]');
  const number = row.querySelector('input[name="phone_number"]');
  if (!country || !number) return;
  const updateExample = () => {
    number.placeholder = country.selectedOptions[0]?.dataset.example || '912345678';
  };
  country.addEventListener('change', updateExample);
  updateExample();
});
