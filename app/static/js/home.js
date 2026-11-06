// Главная Energy Lab: ракета летит по линии маршрута при прокрутке, станции «загораются», слайдер стартов.
(() => {
  document.documentElement.classList.add('js');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // --- маршрут
  const route = document.querySelector('.route');
  const stations = [...document.querySelectorAll('.station')];
  const line = route && route.querySelector('.route-line');
  const end = route && route.querySelector('.route-end');
  const update = () => {
    if (!route) return;
    // линия орбиты заканчивается у финальной планеты
    const stop = end ? end.offsetTop - 6 : route.offsetHeight - 60;
    if (line) line.style.bottom = (route.offsetHeight - stop) + 'px';
    const r = route.getBoundingClientRect();
    const vh = window.innerHeight;
    const p = Math.min(1, Math.max(0, (vh * 0.6 - r.top) / stop));
    route.style.setProperty('--p', (p * 100).toFixed(2) + '%');
    stations.forEach((s) => {
      if (s.getBoundingClientRect().top < vh * 0.72) s.classList.add('is-reached');
    });
    if (end) end.classList.toggle('is-landed', p >= 0.999);
  };
  if (reduce) stations.forEach((s) => s.classList.add('is-reached'));
  let ticking = false;
  window.addEventListener('scroll', () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { update(); ticking = false; });
  }, { passive: true });
  window.addEventListener('resize', update);
  update();
  // при переходе по якорю (например, /#idea после отправки формы) станция сразу видна
  if (location.hash) stations.forEach((s) => s.classList.add('is-reached'));

  // --- слайдер
  document.querySelectorAll('[data-slider]').forEach((slider) => {
    const track = slider.querySelector('.slider-track');
    const slides = track ? track.children.length : 0;
    const count = slider.querySelector('[data-count]');
    let i = 0;
    let timer = null;
    const go = (n) => {
      i = (n + slides) % slides;
      track.style.transform = `translateX(-${i * 100}%)`;
      if (count) count.textContent = `${i + 1} / ${slides}`;
      [...track.children].forEach((el, k) => { el.inert = k !== i; });
      slider.querySelectorAll('[data-go]').forEach((d) => d.setAttribute('aria-current', +d.dataset.go === i ? 'true' : 'false'));
    };
    const auto = () => {
      if (reduce || slides < 2) return;
      clearInterval(timer);
      timer = setInterval(() => go(i + 1), +slider.dataset.interval || 6000);
    };
    slider.querySelector('[data-prev]')?.addEventListener('click', () => { go(i - 1); auto(); });
    slider.querySelector('[data-next]')?.addEventListener('click', () => { go(i + 1); auto(); });
    slider.querySelectorAll('[data-go]').forEach((d) => d.addEventListener('click', () => { go(+d.dataset.go); auto(); }));
    slider.addEventListener('mouseenter', () => clearInterval(timer));
    slider.addEventListener('mouseleave', auto);
    slider.addEventListener('focusin', () => clearInterval(timer));
    if (slides) { go(0); auto(); }
  });

  // --- калькулятор стоимости (та же формула, что app/pricing.py)
  const calc = document.querySelector('[data-calc]');
  if (calc) {
    const cfg = JSON.parse(calc.dataset.calc);
    const $ = (s) => calc.querySelector(s);
    const group = $('#c-group'), guests = $('#c-guests'), hours = $('#c-hours');
    const colors = ['#69ddd9', '#ffb547', '#7b88ff', '#7b88ff', '#7b88ff', '#7b88ff', '#4fd1a1'];
    const rub = (v) => new Intl.NumberFormat('ru-RU').format(Math.round(v)) + ' ₽';
    const render = () => {
      const g = cfg.rates[group.value] || { rate: 300, source: 'norm', n: 0 };
      const n = +guests.value, h = +hours.value;
      calc.querySelector('[data-out="guests"]').textContent = n;
      calc.querySelector('[data-out="hours"]').textContent = String(h).replace('.', ',');
      $('[data-source]').textContent = g.source === 'history'
        ? `Материалы: ${rub(g.rate)} на гостя — среднее по ${g.n} прошедшим мероприятиям`
        : `Материалы: ${rub(g.rate)} на гостя — норматив (прошедших мероприятий пока мало)`;
      const lines = [['Реквизит и материалы', g.rate * Math.max(n, cfg.minGuests), colors[0]],
                     ['Ведущие и актёры', cfg.team * h, colors[1]]];
      calc.querySelectorAll('.calc-opts input:checked').forEach((cb) => {
        const o = cfg.options[cb.value]; lines.push([o[0], o[1], colors[2]]);
      });
      const sub = lines.reduce((a, l) => a + l[1], 0);
      lines.push(['Развитие Lab', sub * cfg.margin, colors[6]]);
      const total = Math.round(sub * (1 + cfg.margin) / 100) * 100;
      $('[data-total]').textContent = rub(total);
      $('[data-per]').textContent = `≈ ${rub(Math.round(total / Math.max(n, 1) / 10) * 10)} с гостя`;
      $('[data-bar]').innerHTML = lines.map((l) => `<span style="width:${(l[1] / (sub * (1 + cfg.margin)) * 100).toFixed(1)}%;background:${l[2]}" title="${l[0]}"></span>`).join('');
      $('[data-lines]').innerHTML = lines.map((l) => `<li><i style="background:${l[2]}"></i><span>${l[0]}</span><b>${rub(l[1])}</b></li>`).join('');
    };
    calc.addEventListener('input', render);
    render();
    // перенести расчёт в заявку
    $('[data-to-request]')?.addEventListener('click', () => {
      const f = document.querySelector('.request-form');
      if (!f) return;
      f.querySelector('#rq-guests').value = guests.value;
      const opt = [...f.querySelectorAll('#rq-fmt option')].find((o) => o.dataset.group === group.value);
      if (opt) f.querySelector('#rq-fmt').value = opt.value;
      const msg = f.querySelector('#rq-msg');
      const extras = [...calc.querySelectorAll('.calc-opts input:checked')].map((cb) => cfg.options[cb.value][0]);
      if (!msg.value) msg.value = `Расчёт на сайте: ${group.value.toLowerCase()} формат, ${guests.value} гостей, ${hours.value} ч` + (extras.length ? `, ${extras.join(', ').toLowerCase()}` : '') + `. Ориентир ${$('[data-total]').textContent}.`;
    });
  }
})();
