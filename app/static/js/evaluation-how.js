// «Как считается оценка»: листалка карточек и живые примеры. Формулы те же, что в app/expertise.
(function () {
  var deck = document.querySelector("[data-deck]");
  if (!deck) return;
  var track = deck.querySelector("[data-track]");
  var cards = Array.prototype.slice.call(track.children);
  var dots = deck.querySelectorAll("[data-go]");
  var cur = 0;
  var fmt = function (v, d) { return v.toFixed(d === undefined ? 2 : d).replace(".", ","); };
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function go(i, focus) {
    cur = Math.max(0, Math.min(cards.length - 1, i));
    track.scrollTo({ left: cards[cur].offsetLeft - cards[0].offsetLeft, behavior: reduce ? "auto" : "smooth" });
    mark();
    if (focus) cards[cur].focus({ preventScroll: true });
  }
  function mark() {
    dots.forEach(function (d, k) { d.setAttribute("aria-current", k === cur ? "step" : "false"); });
    deck.querySelector("[data-prev]").disabled = cur === 0;
    deck.querySelector("[data-next]").disabled = cur === cards.length - 1;
  }
  cards.forEach(function (c) { c.tabIndex = -1; });
  deck.querySelector("[data-prev]").addEventListener("click", function () { go(cur - 1); });
  deck.querySelector("[data-next]").addEventListener("click", function () { go(cur + 1); });
  dots.forEach(function (d) { d.addEventListener("click", function () { go(+d.dataset.go); }); });
  deck.addEventListener("keydown", function (e) {
    if (e.target.matches("input[type=range]")) return;     // стрелки двигают ползунок, а не карточки
    if (e.key === "ArrowRight") { e.preventDefault(); go(cur + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); go(cur - 1); }
  });
  var t;
  track.addEventListener("scroll", function () {             // свайп: какая карточка сейчас в центре
    clearTimeout(t);
    t = setTimeout(function () {
      var best = 0, dist = 1e9;
      cards.forEach(function (c, k) {
        var d = Math.abs(c.offsetLeft - cards[0].offsetLeft - track.scrollLeft);
        if (d < dist) { dist = d; best = k; }
      });
      if (best !== cur) { cur = best; mark(); }
    }, 80);
  });
  mark();

  // 2. шкала
  var scale = deck.querySelector("[data-scale]");
  if (scale) scale.addEventListener("click", function (e) {
    var b = e.target.closest("[data-score]");
    if (!b) return;
    scale.querySelectorAll("[data-score]").forEach(function (x) { x.setAttribute("aria-checked", x === b ? "true" : "false"); });
    deck.querySelector("[data-scale-out]").textContent = b.dataset.text;
    deck.querySelector("[data-scale-note]").classList.toggle("how-is-hot", +b.dataset.score <= 3);
  });

  // 3. карточки отделов переворачиваются
  deck.querySelectorAll("[data-flip]").forEach(function (f) {
    f.addEventListener("click", function () { f.setAttribute("aria-pressed", f.getAttribute("aria-pressed") === "true" ? "false" : "true"); });
  });

  // 4. S = Σ α_d·S_d / Σ α_d по отделам, у которых есть оценки
  var calc = deck.querySelector("[data-calc]");
  function calcS() {
    var num = 0, den = 0, off = 0;
    calc.querySelectorAll(".how-calc-row").forEach(function (row) {
      var r = row.querySelector("input[type=range]"), o = row.querySelector("output"), x = row.querySelector("input[type=checkbox]");
      r.disabled = x.checked;
      o.textContent = x.checked ? "—" : fmt(+r.value, 1);
      if (x.checked) { off++; return; }
      num += +row.dataset.alpha * +r.value; den += +row.dataset.alpha;
    });
    var s = den ? num / den : null, out = calc.querySelector("[data-s]");
    out.textContent = s === null ? "—" : fmt(s);
    out.className = s === null ? "" : "score score-" + (s < 5.5 ? "low" : s < 6.5 ? "mid" : "ok");
    calc.querySelector("[data-s-note]").textContent = s === null ? "никто не оценил" :
      (off ? "вес " + off + (off === 1 ? " отдела" : " отделов") + " разделён между остальными · " : "") +
      (s < 5.5 ? "ниже 5,5 — на переделку" : s < 6.5 ? "ниже 6,5 — на доработку" : "проходит порог");
  }
  if (calc) { calc.addEventListener("input", calcS); calcS(); }

  // 5. согласие экспертов
  var w = deck.querySelector("[data-w]");
  function calcW() {
    var r = w.querySelector("input"), v = +r.value, th = +r.dataset.threshold;
    w.querySelector("[data-w-out]").textContent = fmt(v);
    var order = v >= 0.8 ? ["Квест", "Квиз", "Финал"] : v >= th ? ["Квест", "Финал", "Квиз"] : v >= 0.25 ? ["Финал", "Квест", "Квиз"] : ["Финал", "Квиз", "Квест"];
    w.querySelectorAll("[data-r]").forEach(function (el, k) { el.textContent = order[k]; el.classList.toggle("how-is-diff", order[k] !== ["Квест", "Квиз", "Финал"][k]); });
    w.querySelector("[data-w-verdict]").textContent = v >= th ? "Эксперты согласны — оценке можно доверять." :
      "Эксперты спорят — нужен второй тур Дельфи.";
    w.querySelector("[data-w-verdict]").className = "how-w-verdict " + (v >= th ? "zone-green" : "zone-yellow");
  }
  if (w) { w.addEventListener("input", calcW); calcW(); }

  // 6. карта рисков
  var grid = deck.querySelector("[data-risk]");
  if (grid) grid.addEventListener("click", function (e) {
    var c = e.target.closest(".how-risk-cell");
    if (!c) return;
    grid.querySelectorAll(".how-risk-cell").forEach(function (x) { x.classList.toggle("how-is-on", x === c); });
    var p = +c.dataset.p, i = +c.dataset.i, r = p * i;
    var zone = r <= +grid.dataset.green ? ["зелёная", "блок готов, следим как обычно"] :
      r <= +grid.dataset.yellow ? ["жёлтая", "нужен план Б и ответственный"] : ["красная", "блок переделывают до запуска"];
    var q = 1 - (1 - Math.min(1, r / 100));
    deck.querySelector("[data-risk-out]").innerHTML = "";
    var out = deck.querySelector("[data-risk-out]");
    [["R = " + p + " × " + i + " = " + r, "how-risk-big"], ["Зона " + zone[0] + ": " + zone[1] + ".", ""],
     ["Один такой блок даёт риск провала мероприятия Q ≈ " + Math.round(q * 100) + "%.", "small muted"]].forEach(function (x) {
      var el = document.createElement("p"); el.textContent = x[0]; if (x[1]) el.className = x[1]; out.appendChild(el);
    });
  });

  // 8. правила рекомендации (как app/expertise/forecast.recommend)
  var dec = deck.querySelector("[data-decide]");
  function calcD() {
    var S = +dec.querySelector("#ds").value, W = +dec.querySelector("#dw").value;
    var rounds = dec.querySelector("[data-dr]").checked, red = dec.querySelector("[data-dred]").checked;
    var money = dec.querySelector("[data-dmoney]").checked, wt = +dec.dataset.wt;
    var rej = +dec.dataset.reject, rew = +dec.dataset.rework;
    dec.querySelector("[data-ds-out]").textContent = fmt(S);
    dec.querySelector("[data-dw-out]").textContent = fmt(W);
    var verdict, reasons = [];
    if (S < rej) { verdict = "Отклонить или переработать концепцию"; reasons.push("Итоговая оценка " + fmt(S) + " ниже " + fmt(rej, 1)); }
    else {
      if (red) reasons.push("Есть блок сценария в красной зоне риска");
      if (W < wt && rounds) reasons.push("Эксперты не согласовали оценки: W = " + fmt(W) + " после всех туров");
      if (S < rew) reasons.push("Итоговая оценка " + fmt(S) + " ниже " + fmt(rew, 1));
      verdict = reasons.length ? "Доработать" : "Утвердить";
      if (money) reasons.push("Предупреждение: прогноз затрат выше прогноза выручки");
      if (W < wt && !rounds) reasons.push("Подсказка: W ниже порога — сначала второй тур Дельфи");
    }
    var v = dec.querySelector("[data-dv]");
    v.textContent = verdict;
    v.className = verdict === "Утвердить" ? "zone-green" : verdict === "Доработать" ? "zone-yellow" : "zone-red";
    var ul = dec.querySelector("[data-dreasons]"); ul.innerHTML = "";
    reasons.forEach(function (r) { var li = document.createElement("li"); li.textContent = r; ul.appendChild(li); });
  }
  if (dec) { dec.addEventListener("input", calcD); dec.addEventListener("change", calcD); calcD(); }

  // 9. компетентность: c' = (1 − η)·c + η·(1 − |S_e − r| / (N − 1)), N = 10
  var comp = deck.querySelector("[data-comp]");
  function calcC() {
    var rs = comp.querySelectorAll("input"), outs = comp.querySelectorAll("output");
    var c = +rs[0].value, se = +rs[1].value, r = +rs[2].value, eta = +comp.dataset.eta;
    outs[0].textContent = fmt(c); outs[1].textContent = fmt(se, 1); outs[2].textContent = fmt(r, 1);
    var nc = Math.max(+comp.dataset.lo, Math.min(+comp.dataset.hi, (1 - eta) * c + eta * (1 - Math.abs(se - r) / ((+comp.dataset.scale || 10) - 1))));
    comp.querySelector("[data-c]").textContent = fmt(nc);
    var d = nc - c;
    comp.querySelector("[data-c-note]").textContent = Math.abs(d) < 0.005 ? "почти не изменилась" :
      (d > 0 ? "выросла на " : "снизилась на ") + fmt(Math.abs(d)) + (Math.abs(se - r) <= 1 ? " — прогноз эксперта сбылся" : " — эксперт ошибся на " + fmt(Math.abs(se - r), 1) + " балла");
  }
  if (comp) { comp.addEventListener("input", calcC); calcC(); }
})();
