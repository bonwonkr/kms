"""시네마틱 다큐 오버레이: 레터박스, AI 질문 타이핑 HUD, 다큐 자막, 데이터 그래픽, 효과음."""
import math, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE, OUT, FONTS = sys.argv[1], sys.argv[2], sys.argv[3]
W, H, FPS, DUR = 1920, 1080, 24, 36.3
TITLE = FONTS + "/BlackHanSans.ttf"
BODY = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
BAR = 132  # 2.35:1 레터박스
WHITE = (255, 255, 255)
AMBER = (255, 196, 120)
CYAN = (120, 210, 255)
GREY = (190, 195, 205)

_fc = {}
def F(p, s):
    if (p, s) not in _fc: _fc[(p, s)] = ImageFont.truetype(p, s)
    return _fc[(p, s)]

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def eo(x): x = clamp(x); return 1 - (1 - x) ** 3
def pr(t, s, d): return clamp((t - s) / d)

def txt(text, path, size, fill, spacing=0, shadow=True):
    f = F(path, size)
    l, t, r, b = f.getbbox(text)
    w = r - l + spacing * max(0, len(text) - 1)
    pad = 30
    im = Image.new("RGBA", (int(w) + pad * 2, b - t + pad * 2), (0, 0, 0, 0))
    def draw(d, off, col):
        if spacing:
            x = pad - l
            for ch in text:
                d.text((x + off[0], pad - t + off[1]), ch, font=f, fill=col)
                x += f.getlength(ch) + spacing
        else:
            d.text((pad - l + off[0], pad - t + off[1]), text, font=f, fill=col)
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        draw(ImageDraw.Draw(sh), (0, 3), (0, 0, 0, 200))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(9)))
    draw(ImageDraw.Draw(im), (0, 0), fill)
    return im

def alpha(im, a):
    if a >= 0.999: return im
    r, g, b, al = im.split()
    return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * a))))

def paste(cv, im, x, y, a=1.0, anchor="c", sc=1.0):
    if a <= 0.004: return
    if abs(sc - 1) > 0.003:
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
    im = alpha(im, a)
    if anchor == "c": x, y = x - im.width / 2, y - im.height / 2
    elif anchor == "l": y = y - im.height / 2
    layer = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    layer.paste(im, (int(x), int(y)), im)
    cv.alpha_composite(layer)

# ---------------- 1. AI 질문 HUD (로봇 손 장면 위)
Q = "안산시의 문제가 무엇인가?"
T0, T1, T_ENTER = 0.9, 3.7, 4.0
def typed(t):
    n = int(len(Q) * clamp((t - T0) / (T1 - T0)))
    return Q[:n]
KEY_TIMES = [T0 + (T1 - T0) * (i + 0.5) / len(Q) for i in range(len(Q)) if Q[i] != " "]

def hud(cv, t):
    if t > 5.2: return
    a = eo(pr(t, 0.25, 0.4)) * (1 - pr(t, 4.6, 0.5))
    # 유리 패널
    pw, ph = 1040, 200
    x0, y0 = (W - pw) // 2, 250
    panel = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((0, 0, pw - 1, ph - 1), 22, fill=(10, 18, 32, 150), outline=(120, 210, 255, 140), width=2)
    d.line((30, 88, pw - 30, 88), fill=(120, 210, 255, 70), width=1)
    s = typed(t) if t < T_ENTER else Q
    f = F(BODY, 50)
    d.text((40, 108), s, font=f, fill=WHITE + (255,))
    if t < T_ENTER and int(t * 3) % 2 == 0:
        w = f.getlength(s)
        d.rectangle((46 + w, 112, 50 + w, 162), fill=CYAN + (255,))
    if t >= T_ENTER:
        dots = "분석 중" + "." * (1 + int((t - T_ENTER) * 4) % 3)
        d.text((pw - 220, 120), dots, font=F(BODY, 30), fill=CYAN + (230,))
    paste(cv, panel, x0, y0, a, anchor="tl")
    # 전송 순간 빛 번쩍
    fl = 1 - pr(t, T_ENTER, 0.25)
    if T_ENTER <= t < T_ENTER + 0.25:
        cv.alpha_composite(Image.new("RGBA", (W, H), (180, 230, 255, int(60 * fl))))

# ---------------- 2. 다큐 자막 (아래 레터박스 안)
CAPS = [
    (5.6, 11.0, "안산을 떠올리면, 사람들은 ‘외국인 동네’라고 말합니다."),
    (11.6, 19.3, "하지만 진짜 문제는 숫자에 있습니다. 70.8만에서 61만 명으로."),
    (20.0, 24.5, "일자리 지표는 경기도 1위인데, 청년은 떠납니다."),
    (25.1, 30.0, "이유는 일자리의 질, 주거, 그리고 교통입니다."),
    (30.8, 34.2, "안산다움이, 안산의 답입니다."),
]
CAP_IMG = [(s, e, txt(c, BODY, 40, WHITE, shadow=False)) for s, e, c in CAPS]
def captions(cv, t):
    for s, e, im in CAP_IMG:
        if s <= t <= e + 0.3:
            a = eo(pr(t, s, 0.3)) * (1 - pr(t, e, 0.3))
            paste(cv, im, W / 2, H - BAR / 2, a)

# ---------------- 3. 장면별 그래픽
def chapter(cv, t, s, e, kicker, title, x=140, y=330):
    if not (s <= t <= e): return
    a = eo(pr(t, s, 0.6)) * (1 - pr(t, e - 0.5, 0.5))
    k = txt(kicker, BODY, 30, AMBER, spacing=6)
    ti = txt(title, TITLE, 120, WHITE, spacing=4)
    dx = 30 * (1 - eo(pr(t, s, 0.8)))
    paste(cv, k, x - 30 + dx, y, a, anchor="l")
    lw = int(220 * eo(pr(t, s + 0.2, 0.6)))
    if lw > 0:
        paste(cv, Image.new("RGBA", (lw, 3), AMBER + (230,)), x, y + 40, a, anchor="l")
    paste(cv, ti, x - 30 + dx, y + 125, a, anchor="l")

def source(cv, t, s, e, text):
    if not (s <= t <= e): return
    a = 0.85 * eo(pr(t, s, 0.5)) * (1 - pr(t, e - 0.4, 0.4))
    paste(cv, txt("자료: " + text, BODY, 22, GREY, shadow=True), W - 60, BAR + 40, a, anchor="tl_r")

def paste_right(cv, im, xr, y, a):
    paste(cv, im, xr - im.width, y, a, anchor="tl")

def src(cv, t, s, e, text):
    if not (s <= t <= e): return
    a = 0.85 * eo(pr(t, s, 0.5)) * (1 - pr(t, e - 0.4, 0.4))
    paste_right(cv, txt("자료: " + text, BODY, 22, GREY), W - 40, BAR + 10, a)

def counter(cv, t, s, e):
    if not (s <= t <= e): return
    a = eo(pr(t, s, 0.5)) * (1 - pr(t, e - 0.4, 0.4))
    p = eo(pr(t, s + 0.3, 1.4))
    v = 70.8 - (70.8 - 61.0) * p
    paste(cv, txt("안산시 인구", BODY, 34, GREY, spacing=4), 150, 420, a, anchor="l")
    paste(cv, txt(f"{v:.1f}만", TITLE, 150, WHITE, spacing=2), 140, 545, a, anchor="l")
    paste(cv, txt("2014년 말 70.8만 → 2026년 중반 약 61만(내국인)", BODY, 28, AMBER), 150, 660, a, anchor="l")
    # 하강 그래프 선
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pts = [(1180, 420), (1460, 560), (1700, 590)]
    seg = p * 2
    for i in range(2):
        q = clamp(seg - i)
        if q <= 0: break
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        d.line((x1, y1, x1 + (x2 - x1) * q, y1 + (y2 - y1) * q), fill=AMBER + (int(255 * a),), width=5)
    for i, (x, y) in enumerate(pts):
        if seg >= i:
            d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=WHITE + (int(255 * a),))
    for (x, y), lab in zip(pts, ["70.8", "62.3", "약 61"]):
        d.text((x, y - 40), lab, font=F(TITLE, 34), fill=WHITE + (int(255 * a * clamp(seg - pts.index((x, y)) + 1)),), anchor="mm")
    cv.alpha_composite(layer)

def jobs_vs_youth(cv, t, s, e):
    if not (s <= t <= e): return
    a = eo(pr(t, s, 0.5)) * (1 - pr(t, e - 0.4, 0.4))
    p1 = eo(pr(t, s + 0.2, 0.6)); p2 = eo(pr(t, s + 1.3, 0.6))
    paste(cv, txt("청년친화지수 일자리 부문", BODY, 32, GREY, spacing=3), 150, 400, a * p1, anchor="l")
    paste(cv, txt("경기도 1위", TITLE, 120, WHITE, spacing=2), 140, 505, a * p1, anchor="l")
    n = int(18000 * eo(pr(t, s + 1.3, 1.0)) / 100) * 100
    paste(cv, txt("최근 4년 · 20~39세 청년", BODY, 32, GREY, spacing=3), 1060, 400, a * p2, anchor="l")
    paste(cv, txt(f"-{n / 10000:.1f}만 명", TITLE, 120, AMBER, spacing=2), 1050, 505, a * p2, anchor="l")

def reasons(cv, t, s, e):
    if not (s <= t <= e): return
    out = 1 - pr(t, e - 0.4, 0.4)
    for i, w in enumerate(["일자리의 질", "주거", "교통"]):
        p = eo(pr(t, s + 0.4 + i * 0.6, 0.5))
        paste(cv, txt(w, TITLE, 96, WHITE if i else AMBER, spacing=3), 150 + 30 * (1 - p), 400 + i * 125, p * out, anchor="l")

def finale(cv, t, s):
    if t < s: return
    fade = 1 - pr(t, 35.5, 0.7)
    p = eo(pr(t, s + 0.9, 0.9))
    paste(cv, txt("안산다움이,", TITLE, 84, WHITE, spacing=3), W / 2, 640, p * fade, sc=0.95 + 0.05 * p)
    q = eo(pr(t, s + 1.5, 0.9))
    paste(cv, txt("안산의 답입니다", TITLE, 104, AMBER, spacing=3), W / 2, 760, q * fade, sc=0.95 + 0.05 * q)

END_NOTE = txt("AI 생성 영상 · 출연 인물 사진은 본인 동의를 받아 사용 · 자료: 「안산시 문제점과 도시 이미지 분석」(2026.11)", BODY, 22, GREY, shadow=False)

def render(t, frame):
    cv = frame.convert("RGBA")
    hud(cv, t)
    chapter(cv, t, 5.2, 11.0, "사람들의 인식", "외국인 동네?")
    src(cv, t, 5.2, 11.0, "온라인 커뮤니티 게시글·댓글 (보고서 3장)")
    counter(cv, t, 11.6, 19.5)
    src(cv, t, 11.6, 19.5, "파이낸셜뉴스(2024.10), 서울신문(2026.7)")
    jobs_vs_youth(cv, t, 20.0, 24.6)
    src(cv, t, 20.0, 24.6, "헤럴드K(2026.3.19), 경기신문(2026.6)")
    reasons(cv, t, 25.0, 30.1)
    src(cv, t, 25.0, 30.1, "「안산시 문제점과 도시 이미지 분석」 5장")
    finale(cv, t, 30.6)
    d = ImageDraw.Draw(cv)
    d.rectangle((0, 0, W, BAR), fill=(0, 0, 0, 255))
    d.rectangle((0, H - BAR, W, H), fill=(0, 0, 0, 255))
    captions(cv, t)
    if t > 34.4:
        paste(cv, END_NOTE, W / 2, BAR / 2, 0.8 * eo(pr(t, 34.4, 0.5)) * (1 - pr(t, 35.6, 0.4)))
    a0 = 1 - pr(t, 0, 0.5)
    if a0 > 0: cv.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * a0))))
    if t > 35.7: cv.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * pr(t, 35.7, 0.6)))))
    return cv.convert("RGB")

# ---------------- 사운드: 저음 드론 + 장면 전환 임팩트 + 키보드 클릭 + 상승음
def make_audio(path):
    sr = 48000; n = int(sr * DUR); tt = np.arange(n) / sr
    rng = np.random.default_rng(5)
    out = np.zeros(n)
    def env(s, e, a=1.0, r=1.0):
        g = np.clip((tt - s) / a, 0, 1) * np.clip((e - tt) / r, 0, 1)
        return g
    # 드론 (A단조 → 마지막 C장조)
    def tone(f, s, e, g):
        return (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 2.003 * tt)) * env(s, e, 1.2, 1.5) * g
    for f in (55.0, 82.41, 110.0, 130.81):
        out += tone(f, 0.0, 31.0, 0.05)
    for f in (65.41, 98.0, 130.81, 164.81, 196.0):
        out += tone(f, 30.0, 36.3, 0.05)
    # 저음 임팩트
    def boom(t0, g=0.7):
        i0 = int(t0 * sr); L = int(1.6 * sr); x = np.arange(L) / sr
        s = np.sin(2 * np.pi * (38 + 60 * np.exp(-x * 8)) * x) * np.exp(-x * 2.5)
        nz = np.convolve(rng.standard_normal(L), np.ones(60) / 60, "same") * np.exp(-x * 6) * 0.6
        seg = (s + nz) * g
        out[i0:i0 + L] += seg[: max(0, min(L, n - i0))]
    for c in (4.8, 10.75, 19.1, 24.3, 29.75):
        boom(c, 0.5)
    # 상승음 (각 임팩트 직전)
    for c in (4.8, 29.75):
        s0 = c - 1.4
        m = (tt >= s0) & (tt < c)
        x = tt[m] - s0
        out[m] += np.convolve(rng.standard_normal(m.sum()), np.ones(20) / 20, "same") * (x / 1.4) ** 2 * 0.5
    # 키보드 클릭
    for k in KEY_TIMES + [T_ENTER]:
        i0 = int(k * sr); L = int(0.04 * sr); x = np.arange(L) / sr
        g = 0.55 if k == T_ENTER else rng.uniform(0.25, 0.4)
        out[i0:i0 + L] += (rng.standard_normal(L) * 0.6 + np.sin(2 * np.pi * 180 * x)) * np.exp(-x * 150) * g
    # 피아노풍 단음 (마지막 희망 파트)
    for i, (k, f) in enumerate([(30.6, 523.25), (31.4, 659.25), (32.2, 783.99), (33.0, 659.25), (33.8, 523.25)]):
        i0 = int(k * sr); L = int(1.6 * sr); x = np.arange(L) / sr
        s = (np.sin(2 * np.pi * f * x) + 0.3 * np.sin(4 * np.pi * f * x)) * np.exp(-x * 2.2) * 0.12
        out[i0:i0 + L] += s[: max(0, min(L, n - i0))]
    out *= np.clip((DUR - tt) / 0.6, 0, 1)
    out = out / max(1e-6, np.abs(out).max()) * 0.9
    pcm = (np.repeat(out[:, None], 2, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

if __name__ == "__main__":
    if len(sys.argv) > 4 and sys.argv[4] == "preview":
        for x in sys.argv[5].split(","):
            tt = float(x)
            fr = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(tt), "-i", BASE, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            render(tt, Image.frombytes("RGB", (W, H), fr)).save(f"{OUT}_p{tt:05.2f}.jpg", quality=82)
        sys.exit()
    wav = OUT + "_sfx.wav"
    make_audio(wav)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", BASE, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-af", "loudnorm=I=-16:TP=-1.5", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT + ".mp4"], stdin=subprocess.PIPE)
    i = 0; sz = W * H * 3
    while True:
        buf = dec.stdout.read(sz)
        if len(buf) < sz: break
        enc.stdin.write(render(i / FPS, Image.frombytes("RGB", (W, H), buf)).tobytes())
        i += 1
    enc.stdin.close(); enc.wait(); print("done", i)
