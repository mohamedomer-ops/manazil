(() => {
  const panel = document.querySelector('.market-filter-panel');
  if (panel) {
    const mobile = window.matchMedia('(max-width: 767px)');
    const setMode = () => { panel.open = !mobile.matches; };
    setMode();
    mobile.addEventListener('change', setMode);
  }

  document.querySelectorAll('[data-market-carousel]').forEach((carousel) => {
    const card = carousel.closest('.market-result');
    const image = card.querySelector('.property-card-image');
    const media = card.querySelector('.property-card-media');
    const link = card.querySelector('.market-result-link');
    const counter = card.querySelector('.market-photo-current');
    const sources = Array.from(carousel.querySelector('.market-carousel-sources').content.querySelectorAll('[data-photo-src]'), (node) => node.dataset.photoSrc);
    let index = 0;
    let swipeStart = null;
    let suppressClickUntil = 0;

    const show = (nextIndex) => {
      index = (nextIndex + sources.length) % sources.length;
      image.hidden = false;
      media.querySelector('.property-card-image-placeholder').setAttribute('aria-hidden', 'true');
      image.src = sources[index];
      counter.textContent = String(index + 1);
    };

    carousel.querySelector('.market-carousel-previous').addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      show(index - 1);
    });
    carousel.querySelector('.market-carousel-next').addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      show(index + 1);
    });

    media.addEventListener('pointerdown', (event) => {
      if (event.isPrimary) swipeStart = { id: event.pointerId, x: event.clientX, y: event.clientY };
    });
    media.addEventListener('pointerup', (event) => {
      if (!swipeStart || event.pointerId !== swipeStart.id) return;
      const deltaX = event.clientX - swipeStart.x;
      const deltaY = event.clientY - swipeStart.y;
      swipeStart = null;
      if (Math.abs(deltaX) < 35 || Math.abs(deltaX) < Math.abs(deltaY)) return;
      event.preventDefault();
      suppressClickUntil = Date.now() + 800;
      show(index + (deltaX < 0 ? 1 : -1));
    });
    media.addEventListener('pointercancel', () => { swipeStart = null; });
    link.addEventListener('click', (event) => {
      if (Date.now() < suppressClickUntil) event.preventDefault();
    });
  });
})();
