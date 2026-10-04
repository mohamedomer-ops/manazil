(() => {
  const hero = document.querySelector('[data-home-hero]');
  if (!hero || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const slides = Array.from(hero.querySelectorAll('.home-hero-slide'));
  if (slides.length < 2) return;

  let index = 0;
  if (window.matchMedia('(max-width: 767px)').matches) {
    slides[0].classList.remove('is-active');
    index = slides.length - 1;
    slides[index].classList.add('is-active');
  }
  hero.removeAttribute('data-mobile-initial');
  window.setInterval(() => {
    if (document.hidden) return;
    slides[index].classList.remove('is-active');
    index = (index + 1) % slides.length;
    slides[index].classList.add('is-active');
  }, 6500);
})();
