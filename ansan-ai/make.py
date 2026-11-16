"""안산시 문제 20초 모션그래픽: 키보드 타이핑 → AI 답변 인포그래픽 + 내레이션 자막."""
import math, random, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = sys.argv[1]
FONTS = sys.argv[2]
W, H, FPS, DUR = 1920, 1080, 30, 20.0
TITLE = FONTS + "/BlackHanSans.ttf"
BODY = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

BG = (11, 16, 34)
PANEL = (24, 31, 58)
CYAN = (70, 200, 255)
CORAL = (255, 108, 92)
WHITE = (255, 255, 255)
MUTED = (150, 165, 200)
SKIN = (238, 196, 160)

_fc = {}
def F(path, size):
    k = (path, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def eo(x):
    x = clamp(x); return 1 - (1 - x) ** 3

def eback(x):
    x = clamp(x); c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

def pr(t, s, d):
    return clamp((t - s) / d)

def txt(text, path, size, fill, stroke=0, sfill=(0, 0, 0), shadow=True):
    f = F(path, size)
    l, t, r, b = f.getbbox(text, stroke_width=stroke)
    pad = 24
    im = Image.new("RGBA", (r - l + pad * 2, b - t + pad * 2), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - l + 3, pad - t + 5), text, font=f, fill=(0, 0, 0, 160), stroke_width=stroke, stroke_fill=(0, 0, 0, 160))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(7)))
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill)
    return im

def emoji(ch, size):
    f = F(EMOJI, 109)
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    return im.resize((size, int(im.height * size / im.width)), Image.LANCZOS)

def alpha(im, a):
    if a >= 0.999: return im
    r, g, b, al = im.split()
    return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * a))))

def paste(cv, im, cx, cy, a=1.0, sc=1.0, anchor="c"):
    if a <= 0.004 or sc <= 0.01: return
    if abs(sc - 1) > 0.003:
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
    im = alpha(im, a)
    x = int(cx - im.width / 2) if anchor == "c" else int(cx)
    y = int(cy - im.height / 2)
    layer = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    layer.paste(im, (x, y), im)
    cv.alpha_composite(layer)

def rrect(size, r, fill, outline=None, width=0):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=fill, outline=outline, width=width)
    return im

# ---------------------------------------------------------------- 배경
def make_bg():
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    d = np.sqrt((x - 0.5) ** 2 * 1.6 + (y - 0.35) ** 2)
    glow = np.clip(1 - d * 1.6, 0, 1) ** 2
    arr = np.zeros((H, W, 3))
    for i, (a, b) in enumerate(zip(BG, (30, 48, 96))):
        arr[..., i] = a + (b - a) * glow
    im = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    g = ImageDraw.Draw(im)
    for gx in range(0, W, 80):
        g.line((gx, 0, gx, H), fill=(255, 255, 255, 10))
    for gy in range(0, H, 80):
        g.line((0, gy, W, gy), fill=(255, 255, 255, 10))
    return im

BGIMG = make_bg()

# ---------------------------------------------------------------- 1장: 타이핑
QUESTION = "안산시의 문제가 무엇인가?"
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
COMPOUND = {"ㅢ": "ㅡㅣ", "ㅘ": "ㅗㅏ", "ㅝ": "ㅜㅓ", "ㅚ": "ㅗㅣ", "ㅟ": "ㅜㅣ"}

def syl(c, j, k=" "):
    return chr(0xAC00 + (CHO.index(c) * 21 + JUNG.index(j)) * 28 + JONG.index(k))

def strokes(text):
    """(키 jamo, 그 시점까지 화면에 보일 문자열) 목록 — 두벌식 입력을 흉내낸다."""
    out, done = [], ""
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            c, j, k = CHO[code // 588], JUNG[(code % 588) // 28], JONG[code % 28]
            out.append((c, done + c))
            vs = COMPOUND.get(j, j)
            if len(vs) == 2:
                out.append((vs[0], done + syl(c, vs[0])))
                out.append((vs[1], done + syl(c, j)))
            else:
                out.append((j, done + syl(c, j)))
            if k != " ":
                out.append((k, done + syl(c, j, k)))
        else:
            out.append((ch, done + ch))
        done += ch
    return out

STROKES = strokes(QUESTION)
random.seed(3)
T_TYPE0, T_TYPE1 = 0.55, 3.25
times, acc = [], T_TYPE0
step = (T_TYPE1 - T_TYPE0) / len(STROKES)
for i in range(len(STROKES)):
    times.append(acc)
    acc += step * random.uniform(0.7, 1.3)
scale = (T_TYPE1 - T_TYPE0) / (acc - T_TYPE0)
times = [T_TYPE0 + (x - T_TYPE0) * scale for x in times]
T_ENTER = 3.55

ROWS = [
    list("1234567890"),
    list("ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ"),
    list("ㅁㄴㅇㄹㅎㅗㅓㅏㅣ"),
    list("ㅋㅌㅊㅍㅠㅜㅡ,.?"),
]
KW, KH, GAP = 96, 72, 10
KB_X0, KB_Y0 = 380, 650
KEYPOS = {}
for r, row in enumerate(ROWS):
    off = [0, 36, 64, 100][r]
    for i, k in enumerate(row):
        KEYPOS[k] = (KB_X0 + off + i * (KW + GAP), KB_Y0 + r * (KH + GAP), KW, KH)
er = 2
KEYPOS["ENTER"] = (KB_X0 + 70 + 9 * (KW + GAP), KB_Y0 + er * (KH + GAP), KW * 2 + GAP, KH)
KEYPOS[" "] = (KB_X0 + 300, KB_Y0 + 4 * (KH + GAP), KW * 5 + GAP * 4, KH)
KEYPOS["SHIFT"] = (KB_X0 - 14, KB_Y0 + 3 * (KH + GAP), 104, KH)
LEFT_KEYS = set("ㅂㅈㄷㄱㅅㅁㄴㅇㄹㅎㅋㅌㅊㅍ12345") | {"SHIFT"}

def key_img(label, lit):
    k = rrect((KW, KH), 14, (60, 120, 200, 255) if lit else (36, 44, 78, 255), outline=(90, 110, 160, 255), width=2)
    return k

def make_keyboard():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base = rrect((1220, 450), 36, (20, 25, 46, 255), outline=(60, 72, 110, 255), width=3)
    im.paste(base, (KB_X0 - 44, KB_Y0 - 26), base)
    d = ImageDraw.Draw(im)
    for k, (x, y, w, h) in KEYPOS.items():
        d.rounded_rectangle((x, y + 6, x + w, y + h + 6), 14, fill=(12, 15, 30, 255))
        d.rounded_rectangle((x, y, x + w, y + h), 14, fill=(40, 48, 84, 255), outline=(80, 96, 140, 255), width=2)
        lab = {"ENTER": "Enter", "SHIFT": "Shift", " ": ""}.get(k, k)
        f = F(BODY, 34 if len(lab) == 1 else 28)
        d.text((x + w / 2, y + h / 2), lab, font=f, fill=(200, 210, 235, 255), anchor="mm")
    return im

KEYBOARD = make_keyboard()

def make_monitor():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = rrect((1220, 560), 30, (0, 0, 0, 140)).filter(ImageFilter.GaussianBlur(20))
    im.alpha_composite(sh, (350, 50))
    win = rrect((1200, 540), 28, PANEL + (255,), outline=(70, 86, 130, 255), width=3)
    im.alpha_composite(win, (360, 40))
    d = ImageDraw.Draw(im)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((392 + i * 34, 64, 412 + i * 34, 84), fill=c + (255,))
    d.text((960, 74), "AI 어시스턴트", font=F(BODY, 30), fill=MUTED + (255,), anchor="mm")
    d.line((360, 104, 1560, 104), fill=(60, 74, 115, 255), width=2)
    # AI 인사 말풍선
    d.ellipse((400, 132, 460, 192), fill=CYAN + (255,))
    d.text((430, 162), "AI", font=F(TITLE, 30), fill=BG + (255,), anchor="mm")
    d.rounded_rectangle((478, 136, 900, 190), 20, fill=(40, 50, 90, 255))
    d.text((500, 163), "무엇이든 물어보세요.", font=F(BODY, 30), fill=WHITE + (255,), anchor="lm")
    # 입력창
    d.rounded_rectangle((400, 480, 1520, 552), 22, fill=(14, 19, 40, 255), outline=(80, 100, 150, 255), width=2)
    d.ellipse((1452, 486, 1512, 546), fill=CYAN + (255,))
    d.polygon([(1470, 500), (1500, 516), (1470, 532), (1476, 516)], fill=BG + (255,))
    return im

MONITOR = make_monitor()

def make_hand(flip):
    im = Image.new("RGBA", (380, 460), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = SKIN + (210,)
    d.rounded_rectangle((70, 170, 330, 460), 110, fill=col)  # 손바닥/손목
    xs = [80, 140, 200, 260]
    tops = [70, 30, 40, 90]
    for x, t in zip(xs, tops):
        d.rounded_rectangle((x, t, x + 52, 260), 26, fill=col)
        d.rounded_rectangle((x + 10, t + 8, x + 42, t + 34), 12, fill=(250, 220, 200, 200))  # 손톱
    d.rounded_rectangle((300, 200, 360, 330), 30, fill=col)  # 엄지
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 90), (0, 0), im)
    out = Image.new("RGBA", (400, 480), (0, 0, 0, 0))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), (12, 16))
    out.alpha_composite(im, (0, 0))
    out = out.resize((300, 360), Image.LANCZOS)
    return out.transpose(Image.FLIP_LEFT_RIGHT) if flip else out

HAND_L = make_hand(False)
HAND_R = make_hand(True)

def last_press(t, keyset=None):
    k, tp = None, -9
    for (key, _), tt in zip(STROKES, times):
        kk = "?" if key == "?" else key
        if tt <= t and (keyset is None or (kk in LEFT_KEYS) == keyset):
            k, tp = kk, tt
    if T_ENTER <= t and keyset in (None, False):
        k, tp = "ENTER", T_ENTER
    return k, tp

def typed_text(t):
    s = ""
    for (_, disp), tt in zip(STROKES, times):
        if tt <= t: s = disp
    return s

BUBBLE_Q = None
def scene_typing(cv, t):
    cv.alpha_composite(MONITOR)
    d = ImageDraw.Draw(cv)
    # 입력창 텍스트
    if t < T_ENTER:
        s = typed_text(t)
        f = F(BODY, 36)
        d.text((430, 516), s, font=f, fill=WHITE + (255,), anchor="lm")
        if int(t * 2.5) % 2 == 0 or t < T_TYPE1:
            w = f.getlength(s)
            d.rectangle((434 + w, 498, 438 + w, 536), fill=CYAN + (255,))
    else:
        # 질문 말풍선이 위로 올라감
        p = eo(pr(t, T_ENTER, 0.35))
        bq = txt(QUESTION, BODY, 36, WHITE, shadow=False)
        bw, bh = bq.width + 20, 74
        y = 516 - (516 - 250) * p
        x = 1520 - bw
        bub = rrect((bw, bh), 26, (40, 110, 200, 255))
        paste(cv, bub, x, y, 1, anchor="l")
        paste(cv, bq, x + 10, y, 1, anchor="l")
        # AI 생각 중 점 세 개
        if t > T_ENTER + 0.35:
            d.ellipse((400, 312, 460, 372), fill=CYAN + (255,))
            d.text((430, 342), "AI", font=F(TITLE, 30), fill=BG + (255,), anchor="mm")
            d.rounded_rectangle((478, 316, 640, 368), 20, fill=(40, 50, 90, 255))
            for i in range(3):
                a = 0.4 + 0.6 * abs(math.sin((t * 5) - i * 0.7))
                d.ellipse((508 + i * 40 - 9, 342 - 9, 508 + i * 40 + 9, 342 + 9), fill=(200, 215, 255, int(255 * a)))
    # 키보드 + 눌린 키
    cv.alpha_composite(KEYBOARD)
    for key, tt in list(zip([("?" if k == "?" else k) for k, _ in STROKES], times)) + [("ENTER", T_ENTER)]:
        dt = t - tt
        if 0 <= dt < 0.16:
            x, y, w, h = KEYPOS.get(key, KEYPOS[" "])
            a = 1 - dt / 0.16
            d.rounded_rectangle((x, y + 4, x + w, y + h + 4), 14, fill=(70, 190, 255, int(230 * a)))
            lab = {"ENTER": "Enter", " ": ""}.get(key, key)
            d.text((x + w / 2, y + h / 2 + 4), lab, font=F(BODY, 34 if len(lab) == 1 else 28), fill=(255, 255, 255, 255), anchor="mm")
            if key == "?" and dt < 0.16:
                sx, sy, sw, shh = KEYPOS["SHIFT"]
                d.rounded_rectangle((sx, sy + 4, sx + sw, sy + shh + 4), 14, fill=(70, 190, 255, int(200 * a)))
    # 손
    for left, img, home in [(True, HAND_L, (640, 850)), (False, HAND_R, (1210, 850))]:
        k, tp = last_press(t, left)
        hx, hy = home
        if k is not None and k in KEYPOS:
            x, y, w, h = KEYPOS[k]
            tx = x + w / 2
            dt = t - tp
            pull = math.exp(-max(0, dt) * 4)
            hx = hx + (tx - hx) * 0.35 * pull
            hy = hy + 14 * math.exp(-max(0, dt) * 18)
        hy += 4 * math.sin(t * 3 + (0 if left else 1.5))
        paste(cv, img, hx, hy + 150, 1)

# ---------------------------------------------------------------- 2장: AI 답변
CAPTIONS = [
    (4.9, 7.6, "안산은 지금, ‘떠나는 도시’가 되고 있습니다."),
    (7.7, 10.7, "인구는 약 70만 명에서 61만 명 선까지 줄었고,"),
    (10.8, 13.7, "산단이 늙으며 최근 4년간 청년 약 1만 8천 명이 줄었습니다."),
    (13.8, 16.5, "신안산선 지연, 노후 주거, 악취 문제도 쌓여 있습니다."),
    (16.6, 19.6, "하지만 다문화·산단·시화호는 다른 도시가 흉내 낼 수 없는 자원입니다."),
]
CAP_IMGS = [(s, e, txt(c, BODY, 44, WHITE)) for s, e, c in CAPTIONS]

Q_PILL = txt("Q. " + QUESTION, BODY, 32, WHITE, shadow=False)
AI_TAG = txt("AI 답변", TITLE, 30, BG, shadow=False)

def header(cv, t):
    a = eo(pr(t, 4.7, 0.4)) * (1 - pr(t, 19.5, 0.5))
    pill = rrect((Q_PILL.width + 10, 64), 32, (40, 110, 200, 230))
    paste(cv, pill, 60, 70, a, anchor="l")
    paste(cv, Q_PILL, 65, 70, a, anchor="l")
    tag = rrect((AI_TAG.width, 56), 28, CYAN + (255,))
    paste(cv, tag, W - 60 - tag.width, 70, a, anchor="l")
    paste(cv, AI_TAG, W - 60 - tag.width, 70, a, anchor="l")

def caption(cv, t):
    for s, e, im in CAP_IMGS:
        if s - 0.05 <= t <= e + 0.25:
            a = eo(pr(t, s, 0.25)) * (1 - pr(t, e, 0.25))
            bar = rrect((im.width + 40, 92), 18, (0, 0, 0, 170))
            paste(cv, bar, W / 2, 985, a)
            paste(cv, im, W / 2, 985 + 10 * (1 - eo(pr(t, s, 0.25))), a)

def source(cv, text, a):
    im = txt("출처: " + text, BODY, 24, MUTED, shadow=False)
    paste(cv, im, 60, 900, a, anchor="l")

def seg_a(cv, t):  # 떠나는 도시
    s, e = 4.8, 7.65
    if not (s <= t <= e + 0.3): return
    out = pr(t, e - 0.25, 0.3)
    a1 = eo(pr(t, s + 0.1, 0.4)) * (1 - out)
    paste(cv, A_SUB, W / 2, 330 - 30 * (1 - a1), a1)
    p = pr(t, s + 0.35, 0.5)
    paste(cv, A_TITLE, W / 2, 520, clamp(p * 3) * (1 - out), sc=(0.4 + 0.6 * eback(p)) * (1 + 0.15 * out) if p > 0 else 0)
    # 오른쪽으로 빠져나가는 화살표 흐름
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(14):
        k = ((t - s) * 0.55 + i / 14) % 1
        x = 1300 + k * 650
        y = 380 + (i * 53) % 300
        aa = int(220 * math.sin(k * math.pi) * (1 - out) * eo(pr(t, s + 0.6, 0.4)))
        d.line((x, y, x + 34, y + 0), fill=CORAL + (aa,), width=6)
        d.polygon([(x + 34, y - 12), (x + 56, y), (x + 34, y + 12)], fill=CORAL + (aa,))
        x2 = 620 - k * 650
        d.line((x2, y, x2 - 34, y), fill=CORAL + (aa,), width=6)
        d.polygon([(x2 - 34, y - 12), (x2 - 56, y), (x2 - 34, y + 12)], fill=CORAL + (aa,))
    cv.alpha_composite(layer)
    source(cv, "경인일보, 파이낸셜뉴스, 서울신문(2026.7.21)", a1)

A_SUB = txt("안산은 지금", TITLE, 76, WHITE)
A_TITLE = txt("떠나는 도시", TITLE, 230, CORAL, stroke=4, sfill=(60, 10, 10))

BARS = [(70.8, "70.8", "2014년 말", (40, 120, 200)), (62.3, "62.3", "2024년 9월", (90, 150, 210)), (61.0, "약 61", "2026년 중반(내국인)", CORAL)]
B_TITLE = txt("안산시 인구 (단위: 만 명)", TITLE, 56, WHITE)
B_BADGE = txt("10년 남짓 사이 약 9~10만 명 ↓", BODY, 36, WHITE, shadow=False)

def seg_b(cv, t):
    s, e = 7.65, 10.75
    if not (s - 0.1 <= t <= e + 0.3): return
    out = pr(t, e - 0.25, 0.3)
    a = eo(pr(t, s, 0.35)) * (1 - out)
    paste(cv, B_TITLE, W / 2, 200, a)
    base_y, top_y = 800, 330
    vmin, vmax = 55.0, 72.0
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.line((520, base_y, 1400, base_y), fill=(140, 155, 190, int(255 * a)), width=3)
    for i, (v, lab, xl, col) in enumerate(BARS):
        p = eo(pr(t, s + 0.3 + i * 0.45, 0.6))
        x = 600 + i * 270
        hgt = (v - vmin) / (vmax - vmin) * (base_y - top_y) * p
        d.rounded_rectangle((x, base_y - hgt, x + 170, base_y), 10, fill=col + (int(255 * a),))
        if p > 0.05:
            d.text((x + 85, base_y - hgt - 34), lab, font=F(TITLE, 50), fill=WHITE + (int(255 * a * p),), anchor="mm")
        d.text((x + 85, base_y + 36), xl, font=F(BODY, 30), fill=MUTED + (int(255 * a),), anchor="mm")
    cv.alpha_composite(layer)
    pb = eo(pr(t, s + 1.7, 0.4)) * (1 - out)
    badge = rrect((B_BADGE.width + 10, 70), 35, CORAL + (255,))
    paste(cv, badge, 1500, 300, pb, sc=0.7 + 0.3 * eback(pr(t, s + 1.7, 0.4)))
    paste(cv, B_BADGE, 1500, 300, pb, sc=0.7 + 0.3 * eback(pr(t, s + 1.7, 0.4)))
    source(cv, "파이낸셜뉴스(2024.10), 서울신문(2026.7) · 세로축 55만 명부터, 기사별 기준 다를 수 있음", a)

C_LABEL = txt("최근 4년 · 20~39세 청년", BODY, 44, MUTED)
C_CHAIN = ["일자리 감소", "청년 유출", "인구 감소", "소비 위축"]
C_CHAIN_IMG = [txt(c, TITLE, 46, WHITE, shadow=False) for c in C_CHAIN]
FACTORY = emoji("🏭", 120)

def seg_c(cv, t):
    s, e = 10.75, 13.75
    if not (s - 0.1 <= t <= e + 0.3): return
    out = pr(t, e - 0.25, 0.3)
    a = eo(pr(t, s, 0.35)) * (1 - out)
    paste(cv, FACTORY, W / 2, 215, a, sc=0.8 + 0.2 * eback(pr(t, s, 0.4)))
    n = int(18000 * eo(pr(t, s + 0.2, 1.1)) / 100) * 100
    num = txt(f"약 {n // 10000}만 {n % 10000 // 1000}천 명 ↓" if n >= 10000 else f"약 {n:,}명 ↓", TITLE, 150, CORAL, stroke=3, sfill=(60, 10, 10))
    paste(cv, num, W / 2, 400, a)
    paste(cv, C_LABEL, W / 2, 520, a)
    # 쇠퇴 고리
    total_w = sum(im.width + 60 for im in C_CHAIN_IMG) + 3 * 50
    x = W / 2 - total_w / 2
    for i, im in enumerate(C_CHAIN_IMG):
        p = eo(pr(t, s + 1.0 + i * 0.3, 0.35)) * (1 - out)
        chip = rrect((im.width + 40, 84), 42, (40, 50, 90, 255), outline=CORAL + (255,), width=3)
        paste(cv, chip, x, 680 + 20 * (1 - p), p, anchor="l")
        paste(cv, im, x + 20, 680 + 20 * (1 - p), p, anchor="l")
        x += chip.width + 20
        if i < 3:
            paste(cv, ARROW, x + 15, 680, p)
            x += 50
    source(cv, "경기일보(2020.10.14), 경기신문(2026.6), 헤럴드K(2026.1.4)", a)

ARROW = txt("→", BODY, 50, CORAL, shadow=False)

D_CARDS = [("🚇", "교통", "신안산선 개통 지연"), ("🏢", "주거", "40년 넘은 노후 단지"), ("🏭", "환경", "악취 · 소각 용량 부족")]
def make_card(em, head, body):
    c = rrect((440, 400), 30, (30, 40, 76, 245), outline=(80, 100, 160, 255), width=3)
    e = emoji(em, 120)
    c.alpha_composite(e, (220 - e.width // 2, 50))
    h = txt(head, TITLE, 64, CYAN, shadow=False)
    c.alpha_composite(h, (220 - h.width // 2, 190))
    b = txt(body, BODY, 34, WHITE, shadow=False)
    c.alpha_composite(b, (220 - b.width // 2, 290))
    return c
D_IMGS = [make_card(*c) for c in D_CARDS]
D_TITLE = txt("생활 불만도 쌓여 있습니다", TITLE, 60, WHITE)

def seg_d(cv, t):
    s, e = 13.75, 16.55
    if not (s - 0.1 <= t <= e + 0.3): return
    out = pr(t, e - 0.25, 0.3)
    a = eo(pr(t, s, 0.35)) * (1 - out)
    paste(cv, D_TITLE, W / 2, 210, a)
    for i, im in enumerate(D_IMGS):
        p = pr(t, s + 0.2 + i * 0.25, 0.45)
        paste(cv, im, 470 + i * 490, 540 + 60 * (1 - eo(p)), clamp(p * 2) * (1 - out), sc=0.85 + 0.15 * eback(p))
    source(cv, "세계일보(2025.6.30), 서울신문(2026.7.22), 스마트투데이(2026.3), 경기일보(2026.3.9)", a)

E_BUT = txt("하지만", TITLE, 80, CYAN)
E_CHIPS = ["외국인 주민 13~15%", "전국 유일 다문화마을특구", "반월·시화 국가산단", "시화호와 바다"]
E_CHIP_IMG = [txt(c, BODY, 34, WHITE, shadow=False) for c in E_CHIPS]
E_TITLE = txt("다른 도시가 흉내 낼 수 없는 자원", TITLE, 96, WHITE, stroke=3, sfill=(10, 40, 80))

def seg_e(cv, t):
    s = 16.55
    if t < s - 0.1: return
    fade = 1 - pr(t, 19.55, 0.45)
    a = eo(pr(t, s, 0.35)) * fade
    paste(cv, E_BUT, W / 2, 230, a, sc=0.7 + 0.3 * eback(pr(t, s, 0.4)))
    chips = [rrect((im.width + 50, 92), 46, (30, 70, 130, 255), outline=CYAN + (255,), width=3) for im in E_CHIP_IMG]
    total = sum(c.width for c in chips) + 24 * 3
    x = W / 2 - total / 2
    for i, (im, chip) in enumerate(zip(E_CHIP_IMG, chips)):
        p = pr(t, s + 0.3 + i * 0.2, 0.4)
        cx = x + chip.width / 2
        paste(cv, chip, cx, 440, clamp(p * 2) * fade, sc=0.8 + 0.2 * eback(p))
        paste(cv, im, cx, 440, clamp(p * 2) * fade, sc=0.8 + 0.2 * eback(p))
        x += chip.width + 24
    p = pr(t, s + 1.3, 0.5)
    paste(cv, E_TITLE, W / 2, 660, clamp(p * 2) * fade, sc=0.7 + 0.3 * eback(p))
    source(cv, "경기일보(2026.1), 「안산시 문제점과 도시 이미지 분석」 종합 시사점", a)

def render(t):
    cv = BGIMG.copy()
    if t < 4.85:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        scene_typing(layer, t)
        z = pr(t, 4.25, 0.6)
        if z > 0:  # 화면 안으로 줌인
            sc = 1 + 1.6 * z ** 2
            w, h = int(W / sc), int(H / sc)
            cx, cy = 960, 300
            x0, y0 = int(cx - w / 2 * (cx / 960)), int(cy - h / 2 * (cy / 540))
            x0 = max(0, min(W - w, int(cx - w / 2))); y0 = max(0, min(H - h, int(cy - h / 2)))
            layer = layer.crop((x0, y0, x0 + w, y0 + h)).resize((W, H), Image.BILINEAR)
            layer = alpha(layer, 1 - z)
        cv.alpha_composite(layer)
        a0 = 1 - pr(t, 0, 0.4)
        if a0 > 0:
            cv.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * a0))))
    if t >= 4.6:
        header(cv, t)
        seg_a(cv, t); seg_b(cv, t); seg_c(cv, t); seg_d(cv, t); seg_e(cv, t)
        caption(cv, t)
    if t > 19.6:
        cv.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * pr(t, 19.6, 0.4)))))
    return cv.convert("RGB")

# ---------------------------------------------------------------- 효과음 (키보드 클릭)
def make_audio(path):
    sr = 48000
    n = int(sr * DUR)
    buf = np.zeros(n)
    rng = np.random.default_rng(1)
    def click(t0, gain, length=0.035, tone=2200):
        i0 = int(t0 * sr); L = int(length * sr)
        tt = np.arange(L) / sr
        env = np.exp(-tt * 180)
        sig = rng.standard_normal(L) * 0.5 + np.sin(2 * np.pi * tone * tt) * 0.3
        sig += np.sin(2 * np.pi * 160 * tt) * np.exp(-tt * 60) * 0.8
        buf[i0:i0 + L] += sig * env * gain
    for tt in times:
        click(tt, rng.uniform(0.25, 0.4), tone=rng.uniform(1800, 2600))
    click(T_ENTER, 0.6, length=0.08, tone=1200)
    # 말풍선 전송 '뿅'
    i0 = int((T_ENTER + 0.05) * sr); L = int(0.18 * sr); tt = np.arange(L) / sr
    buf[i0:i0 + L] += np.sin(2 * np.pi * (600 + 1400 * tt / 0.18) * tt) * np.exp(-tt * 18) * 0.25
    buf = np.clip(buf, -1, 1)
    pcm = (np.repeat(buf[:, None], 2, axis=1) * 32767 * 0.8).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "preview":
        for x in sys.argv[4].split(","):
            render(float(x)).save(f"{OUT}/p_{float(x):05.2f}.jpg", quality=80)
        sys.exit()
    make_audio(OUT + "/sfx.wav")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-i", OUT + "/sfx.wav", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT + "/ansan_ai_20s.mp4"], stdin=subprocess.PIPE)
    for i in range(int(DUR * FPS)):
        enc.stdin.write(render(i / FPS).tobytes())
        if i % 120 == 0: print("frame", i, flush=True)
    enc.stdin.close(); enc.wait(); print("done")
