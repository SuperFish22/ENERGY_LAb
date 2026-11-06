"""Генератор комиксов FAQ (оригинальные персонажи Energy Lab). Запуск: python docs/faq/make_comics.py

Персонажи:
  Капитан Лаба — руководитель полёта в скафандре с красной полосой ENERGY;
  Искра — маленькая ракета-стажёр, которая задаёт вопросы.
"""
import random
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).parent / "img"
NIGHT, SPACE, ORBIT, STAR, MIST = "#0f1638", "#18214d", "#2c3878", "#f4f2ff", "#a9b4e8"
IGNITE, FLAME, AURORA = "#e5483b", "#ffb547", "#4fd1a1"
FONT = "Golos Text, PT Sans, Arial, sans-serif"
DISPLAY = "Unbounded, Golos Text, Arial, sans-serif"
PW, PH, GAP, TOP = 300, 300, 20, 64


def stars(seed, w, h, n=26):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        x, y, r = rnd.uniform(6, w - 6), rnd.uniform(6, h - 6), rnd.choice([0.8, 1, 1.2, 1.8])
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{STAR}" opacity="{rnd.uniform(.3, .9):.2f}"/>')
    return "".join(out)


def captain(x, y, s=1.0, mood="calm", arm="down"):
    """Капитан: x,y — центр ступней."""
    eyes = {"calm": f'<circle cx="-9" cy="-4" r="3" fill="{STAR}"/><circle cx="9" cy="-4" r="3" fill="{STAR}"/>',
            "happy": f'<path d="M-13 -3 q4 -6 8 0 M5 -3 q4 -6 8 0" stroke="{STAR}" stroke-width="3" fill="none" '
                     'stroke-linecap="round"/>',
            "serious": f'<rect x="-13" y="-6" width="8" height="3" rx="1.5" fill="{STAR}"/>'
                       f'<rect x="5" y="-6" width="8" height="3" rx="1.5" fill="{STAR}"/>'}[mood]
    mouth = {"calm": "M-6 8 q6 4 12 0", "happy": "M-8 6 q8 9 16 0", "serious": "M-6 9 h12"}[mood]
    arm_r = {"down": "M26 -70 q16 22 10 44", "up": "M26 -70 q22 -16 18 -46", "point": "M26 -70 q30 0 46 -10"}[arm]
    return f'''<g transform="translate({x} {y}) scale({s})">
  <ellipse cx="0" cy="2" rx="38" ry="6" fill="#000" opacity=".25"/>
  <rect x="-24" y="-40" width="18" height="40" rx="8" fill="{STAR}"/><rect x="6" y="-40" width="18" height="40" rx="8" fill="{STAR}"/>
  <rect x="-30" y="-100" width="60" height="68" rx="22" fill="{STAR}"/>
  <rect x="-30" y="-78" width="60" height="10" fill="{IGNITE}"/>
  <rect x="-12" y="-62" width="24" height="16" rx="4" fill="{ORBIT}"/><circle cx="-4" cy="-54" r="3" fill="{AURORA}"/><circle cx="5" cy="-54" r="3" fill="{FLAME}"/>
  <path d="M-26 -70 q-16 22 -10 44" stroke="{STAR}" stroke-width="14" fill="none" stroke-linecap="round"/>
  <path d="{arm_r}" stroke="{STAR}" stroke-width="14" fill="none" stroke-linecap="round"/>
  <g transform="translate(0 -128)">
    <circle r="36" fill="{STAR}"/><rect x="-27" y="-22" width="54" height="40" rx="18" fill="{NIGHT}"/>
    <path d="M-20 -14 q8 -6 16 -4" stroke="{MIST}" stroke-width="3" fill="none" stroke-linecap="round" opacity=".7"/>
    {eyes}<path d="{mouth}" stroke="{STAR}" stroke-width="2.5" fill="none" stroke-linecap="round"/>
    <rect x="-3" y="-48" width="6" height="14" rx="3" fill="{IGNITE}"/><circle cy="-50" r="5" fill="{IGNITE}"/>
  </g>
</g>'''


def iskra(x, y, s=1.0, mood="curious", fire=False, tilt=0):
    """Искра: x,y — низ корпуса."""
    face = {"curious": f'<circle cx="-5" cy="0" r="3" fill="{NIGHT}"/><circle cx="6" cy="-1" r="3.6" fill="{NIGHT}"/>',
            "happy": f'<path d="M-9 0 q4 -5 8 0 M2 0 q4 -5 8 0" stroke="{NIGHT}" stroke-width="2.5" fill="none" '
                     'stroke-linecap="round"/><path d="M-5 6 q5 5 10 0" stroke="' + NIGHT
                     + '" stroke-width="2.2" fill="none" stroke-linecap="round"/>',
            "worried": f'<circle cx="-5" cy="1" r="3" fill="{NIGHT}"/><circle cx="6" cy="1" r="3" fill="{NIGHT}"/>'
                       f'<path d="M-10 -7 l8 3 M11 -7 l-8 3" stroke="{NIGHT}" stroke-width="2" stroke-linecap="round"/>'
                       f'<path d="M-4 9 q4 -3 8 0" stroke="{NIGHT}" stroke-width="2" fill="none"/>'}[mood]
    flame = (f'<path d="M-12 4 q12 46 24 0 q-6 14 -12 30 q-6 -16 -12 -30z" fill="{FLAME}"/>'
             f'<path d="M-6 4 q6 24 12 0z" fill="{IGNITE}"/>') if fire else ""
    return f'''<g transform="translate({x} {y}) rotate({tilt}) scale({s})">
  {flame}
  <path d="M-22 -10 l-14 18 l16 -4z M22 -10 l14 18 l-16 -4z" fill="{IGNITE}"/>
  <path d="M0 -110 C30 -80 30 -30 22 0 H-22 C-30 -30 -30 -80 0 -110z" fill="{STAR}"/>
  <path d="M0 -110 C12 -98 20 -88 24 -76 H-24 C-20 -88 -12 -98 0 -110z" fill="{IGNITE}"/>
  <circle cx="0" cy="-48" r="18" fill="{MIST}"/><circle cx="0" cy="-48" r="14" fill="#dfe5ff"/>
  <g transform="translate(0 -48)">{face}</g>
  <rect x="-14" y="-16" width="28" height="5" rx="2.5" fill="{ORBIT}"/>
</g>'''


def bubble(x, y, w, lines, tail=(0, 0), who="captain", size=15):
    longest = max(len(t) for t in lines)
    while longest * size * 0.55 + 26 > PW - 16 and size > 11:      # не вылезать за кадр
        size -= 1
    w = max(w, int(longest * size * 0.55 + 26))
    x = max(8, min(x, PW - 8 - w))
    h = 18 + len(lines) * (size + 5)
    tx, ty = tail
    fill, ink = (STAR, NIGHT) if who == "captain" else (FLAME, NIGHT)
    text = "".join(f'<tspan x="{x + 12}" dy="{size + 5 if i else size + 6}">{escape(t)}</tspan>'
                   for i, t in enumerate(lines))
    # хвост от нижнего края пузыря к говорящему
    bx = min(max(tx, x + 18), x + w - 18)
    if tx > x + w:                      # говорящий справа — хвост из правого края
        tail_d = f"M{x + w - 1} {y + h / 2 - 9} L{tx} {ty} L{x + w - 1} {y + h / 2 + 7}z"
    else:
        tail_d = f"M{bx - 10} {y + h - 1} L{tx} {ty} L{bx + 10} {y + h - 1}z"
    return (f'<path d="{tail_d}" fill="{fill}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}"/>'
            f'<text x="{x + 12}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{ink}">{text}</text>')


def caption(x, y, w, t):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="26" fill="{ORBIT}"/>'
            f'<text x="{x + 10}" y="{y + 18}" font-family="{FONT}" font-size="13" fill="{MIST}">{escape(t)}</text>')


def screen(x, y, w, h, title, rows):
    """Мини-экран Системы внутри кадра."""
    body = "".join(f'<text x="{x + 12}" y="{y + 46 + i * 22}" font-family="{FONT}" font-size="13" '
                   f'fill="{c}">{escape(t)}</text>' for i, (t, c) in enumerate(rows))
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{SPACE}" stroke="{MIST}" stroke-width="1.5"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="26" rx="10" fill="{ORBIT}"/>'
            f'<rect x="{x}" y="{y + 16}" width="{w}" height="10" fill="{ORBIT}"/>'
            f'<text x="{x + 12}" y="{y + 18}" font-family="{FONT}" font-size="12" fill="{STAR}">{escape(title)}</text>'
            + body)


def strip(name, title, panels):
    n = len(panels)
    W = GAP + n * (PW + GAP)
    H = TOP + PH + GAP
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
             f'role="img" aria-label="{escape(title)}">',
             f'<rect width="{W}" height="{H}" fill="{NIGHT}"/>',
             f'<text x="{GAP}" y="42" font-family="{DISPLAY}" font-size="22" font-weight="600" fill="{STAR}">'
             f'{escape(title)}</text>']
    for i, content in enumerate(panels):
        px = GAP + i * (PW + GAP)
        parts.append(f'<g transform="translate({px} {TOP})"><clipPath id="c{name}{i}"><rect width="{PW}" '
                     f'height="{PH}" rx="16"/></clipPath><g clip-path="url(#c{name}{i})">'
                     f'<rect width="{PW}" height="{PH}" fill="{SPACE}"/>{stars(name + str(i), PW, PH)}'
                     f'{content}</g><rect width="{PW}" height="{PH}" rx="16" fill="none" stroke="{ORBIT}" '
                     f'stroke-width="3"/></g>')
    parts.append("</svg>")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.svg").write_text("".join(parts), encoding="utf-8")


PLANET = f'<circle cx="250" cy="330" r="110" fill="{ORBIT}"/><circle cx="210" cy="300" r="14" fill="{SPACE}" opacity=".6"/>'
GROUND = f'<rect y="270" width="{PW}" height="40" fill="{ORBIT}"/>'

strip("01-vhod", "Как попасть в Центр управления?", [
    GROUND + iskra(80, 270, mood="worried") + captain(215, 270)
    + bubble(14, 14, 200, ["Хочу в экипаж!", "Где кнопка", "«Регистрация»?"], (80, 150), "iskra"),
    GROUND + captain(80, 270, mood="happy", arm="point")
    + f'<rect x="170" y="150" width="110" height="70" rx="8" fill="{STAR}"/>'
      f'<path d="M170 150 l55 40 l55 -40" stroke="{ORBIT}" stroke-width="3" fill="none"/>'
    + bubble(110, 14, 180, ["Её нет. Руководитель", "присылает ссылку-", "приглашение на 7 дней"], (90, 120)),
    GROUND + iskra(150, 270, mood="happy", fire=True)
    + bubble(16, 14, 268, ["Открыла ссылку, имя, пароль", "от 8 символов, согласие —", "и я в «Центре управления»!"],
             (150, 150), "iskra"),
])

strip("02-stancii", "Почему проект не уходит на экспертизу?", [
    screen(20, 20, 260, 130, "Ночь в музее · Сборка", [("Станции: 0", FLAME), ("[Отправить на экспертизу]", MIST)])
    + GROUND + iskra(215, 270, mood="worried")
    + bubble(20, 175, 110, ["Не пускает!"], (205, 225), "iskra", 14),
    GROUND + captain(150, 270, arm="up")
    + bubble(14, 14, 272, ["Ракета без ступеней не летит.", "Добавь хотя бы одну станцию:", "вкладка «Станции»."],
             (150, 130)),
    screen(20, 20, 260, 140, "Станции", [("1. Вход в музей · 15 мин", STAR), ("2. Лаборатория · 25 мин", STAR),
                                         ("3. Зал реликвии · 20 мин", STAR)])
    + GROUND + iskra(225, 270, mood="happy", fire=True, tilt=-8)
    + bubble(14, 176, 128, ["Предстартовые", "проверки!"], (205, 225), "iskra", 14),
])

strip("03-ball", "Зачем комментарий, если ставлю 1 или 2?", [
    screen(20, 20, 260, 110, "Оценка · Технический", [("Свет и звук:  ① ● ③ ④ ⑤", STAR),
                                                      ("Комментарий: …", MIST)])
    + GROUND + iskra(225, 270, mood="curious")
    + bubble(14, 160, 150, ["Поставлю 2 и всё.", "Зачем писать?"], (205, 222), "iskra", 14),
    GROUND + captain(150, 270, mood="serious")
    + bubble(14, 14, 272, ["Низкий балл без причины —", "это тревога без адреса.", "Автору нужно знать, что чинить."],
             (150, 130)),
    GROUND + captain(90, 270, mood="happy") + iskra(220, 270, mood="happy")
    + bubble(150, 14, 140, ["«Дым-машина", "слабая для зала", "на 60 мест»"], (215, 150), "iskra", 14)
    + bubble(14, 14, 110, ["Вот это", "помогает!"], (80, 100), "captain", 14),
])

strip("04-risk", "Что такое «красная» станция?", [
    GROUND + iskra(80, 270, mood="curious") + captain(220, 270)
    + bubble(14, 14, 190, ["Почему у станции", "загорелось красное?"], (80, 150), "iskra"),
    f'<text x="26" y="70" font-family="{DISPLAY}" font-size="26" fill="{STAR}">R = P × I</text>'
    f'<text x="26" y="100" font-family="{FONT}" font-size="13" fill="{MIST}">вероятность провала × тяжесть</text>'
    + "".join(f'<rect x="{26 + i * 84}" y="130" width="76" height="60" rx="8" fill="{c}"/>'
              f'<text x="{40 + i * 84}" y="158" font-family="{FONT}" font-size="14" fill="{NIGHT}">{a}</text>'
              f'<text x="{40 + i * 84}" y="178" font-family="{FONT}" font-size="12" fill="{NIGHT}">{b}</text>'
              for i, (c, a, b) in enumerate([(AURORA, "1–6", "норма"), (FLAME, "7–14", "план Б"),
                                             (IGNITE, "15–25", "чинить")]))
    + GROUND + captain(240, 272, s=.42, arm="up"),
    GROUND + iskra(120, 270, mood="worried") + captain(230, 270, s=.9, mood="serious")
    + bubble(14, 14, 272, ["Красная станция — и система", "советует «Доработать».", "Сначала безопасность, потом старт."],
             (220, 130)),
])

strip("05-bot", "Как подружить кабинет с ботом?", [
    screen(20, 20, 260, 120, "Профиль и бот", [("[Получить код привязки]", MIST), ("Код: 482 913 · до 18:40", FLAME)])
    + GROUND + iskra(150, 270, mood="curious"),
    f'<rect x="60" y="30" width="180" height="230" rx="22" fill="{NIGHT}" stroke="{MIST}" stroke-width="2"/>'
    f'<rect x="80" y="70" width="140" height="30" rx="12" fill="{FLAME}"/>'
    f'<text x="92" y="90" font-family="{FONT}" font-size="14" fill="{NIGHT}">/link 482913</text>'
    f'<rect x="80" y="112" width="140" height="48" rx="12" fill="{ORBIT}"/>'
    f'<text x="92" y="132" font-family="{FONT}" font-size="12" fill="{STAR}">Готово, Искра.</text>'
    f'<text x="92" y="150" font-family="{FONT}" font-size="12" fill="{STAR}">Аккаунт привязан.</text>',
    GROUND + iskra(80, 270, mood="happy") + captain(220, 270, mood="happy")
    + bubble(14, 14, 272, ["Теперь /tasks — мои задачи,", "/ask — вопрос своему отделу.", "Код живёт 10 минут!"],
             (80, 150), "iskra"),
])

strip("06-sos", "Что делать, если случилось что-то серьёзное?", [
    GROUND + iskra(150, 270, mood="worried")
    + bubble(40, 20, 220, ["Гостю стало плохо", "на станции!"], (150, 150), "iskra"),
    f'<circle cx="150" cy="110" r="70" fill="{IGNITE}"/>'
    f'<text x="150" y="132" text-anchor="middle" font-family="{DISPLAY}" font-size="56" fill="{STAR}">112</text>'
    + GROUND + captain(150, 270, s=.6, mood="serious", arm="up"),
    GROUND + captain(90, 270, mood="serious") + iskra(225, 270, mood="curious")
    + bubble(14, 14, 272, ["Сначала 112. Потом /sos в боте —", "сообщение получат все дежурные", "руководители, на доску не уйдёт."],
             (95, 130)),
])

strip("07-prognoz", "Откуда система знает, сколько придёт гостей?", [
    GROUND + iskra(80, 270, mood="curious") + captain(220, 270)
    + bubble(14, 14, 200, ["Это гадание", "на звёздах?"], (80, 150), "iskra"),
    "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}"/>' for x, y, r, c in
            [(150, 130, 14, FLAME), (90, 90, 9, MIST), (210, 100, 9, MIST), (120, 190, 9, MIST),
             (230, 200, 7, ORBIT), (60, 200, 7, ORBIT)])
    + "".join(f'<line x1="150" y1="130" x2="{x}" y2="{y}" stroke="{FLAME}" stroke-dasharray="4 4"/>'
              for x, y in [(90, 90), (210, 100), (120, 190)])
    + f'<text x="20" y="40" font-family="{FONT}" font-size="14" fill="{STAR}">Ищем 3 самых похожих прошлых</text>'
      f'<text x="20" y="58" font-family="{FONT}" font-size="14" fill="{STAR}">мероприятия: формат, цена, зал,</text>'
      f'<text x="20" y="76" font-family="{FONT}" font-size="14" fill="{STAR}">сезон, оценка экспертов</text>'
    + GROUND,
    GROUND + captain(150, 270, mood="happy")
    + bubble(14, 14, 272, ["Не гадание — опыт. Чем больше", "«разборов полёта» внесено,", "тем точнее прогноз."], (150, 130)),
])

strip("08-reshenie", "Кто решает, летим или нет?", [
    screen(20, 20, 260, 110, "Прогноз и решение", [("Рекомендация: Доработать", FLAME),
                                                   ("• станция 3 в красной зоне", MIST)])
    + GROUND + iskra(225, 270, mood="worried")
    + bubble(14, 160, 150, ["Машина сказала", "«нет»?"], (205, 222), "iskra", 14),
    GROUND + captain(150, 270, arm="point")
    + bubble(14, 14, 272, ["Система только советует и", "объясняет почему. Решают", "руководители: Александр, Олег, Катя."],
             (150, 130)),
    GROUND + iskra(150, 270, mood="happy", fire=True)
    + bubble(14, 14, 272, ["Утвердить, вернуть с комментарием", "или отклонить. А заключение", "можно распечатать в PDF."],
             (150, 150), "iskra"),
])

if __name__ == "__main__":
    print(sorted(p.name for p in OUT.glob("*.svg")))
