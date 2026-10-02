(() => {
  const hero = document.querySelector('[data-home-hero]');
  if (!hero || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const slides = Array.from(hero.querySelectorAll('.home-hero-slide'));
  if (slides.length < 2) return;

  let index = 0;
  window.setInterval(() => {
    if (document.hidden) return;
    slides[index].classList.remove('is-active');
    index = (index + 1) % slides.length;
    slides[index].classList.add('is-active');
  }, 6500);
})();
