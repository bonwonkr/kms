"""배경음악(직접 합성) + 장면 전환 효과음 + 기존 키보드 효과음을 섞어 wav로 저장."""
import sys, wave
import numpy as np

SFX, OUT = sys.argv[1], sys.argv[2]
SR, DUR = 48000, 20.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)

def note(m):
    return 440.0 * 2 ** ((m - 69) / 12)

def env_seg(s, e, a=0.3, r=0.6):
    g = np.zeros(N)
    i0, i1 = int(s * SR), int(min(e, DUR) * SR)
    L = i1 - i0
    if L <= 0: return g
    x = np.arange(L) / SR
    g[i0:i1] = np.minimum(1, x / a) * np.minimum(1, (L / SR - x) / r)
    return g

def pad(chord, s, e, gain):
    out = np.zeros(N)
    g = env_seg(s, e, 0.6, 0.8)
    for m in chord:
        f = note(m)
        for det in (-0.12, 0.12):
            ff = f * 2 ** (det / 12)
            out += (np.sin(2 * np.pi * ff * t) + 0.3 * np.sin(2 * np.pi * 2 * ff * t)) * g
    return out * gain / len(chord)

music = np.zeros(N)
# 4.6초부터 음악 시작. 단조 진행 → 16.6초 '하지만'에서 장조로 전환
prog = [
    (4.6, 7.65, [45, 52, 57, 60, 64]),    # Am
    (7.65, 10.75, [41, 48, 53, 57, 60]),  # F
    (10.75, 13.75, [43, 50, 55, 59, 62]), # G
    (13.75, 16.55, [40, 47, 52, 55, 59]), # Em
    (16.55, 20.0, [48, 55, 60, 64, 67]),  # C (밝게)
]
for s, e, ch in prog:
    music += pad(ch, s - 0.15, e + 0.35, 0.10)

# 베이스 펄스 + 킥 (100 BPM)
beat = 60 / 100
bt = 4.8
while bt < 19.6:
    i0 = int(bt * SR); L = int(0.25 * SR); x = np.arange(L) / SR
    kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-x * 30)) * x) * np.exp(-x * 9)
    music[i0:i0 + L] += kick[: max(0, min(L, N - i0))] * 0.32
    # 하이햇 (엇박)
    h0 = int((bt + beat / 2) * SR); HL = int(0.05 * SR)
    hat = rng.standard_normal(HL) * np.exp(-np.arange(HL) / SR * 90)
    hat = np.diff(hat, prepend=0)
    if h0 + HL < N: music[h0:h0 + HL] += hat * 0.05
    bt += beat

# 아르페지오 (분위기용, 작게)
for s, e, ch in prog:
    k, x0 = 0, s
    while x0 < e - 0.05:
        f = note(ch[2 + k % 3] + 12)
        i0 = int(x0 * SR); L = int(0.22 * SR); x = np.arange(L) / SR
        tone = np.sin(2 * np.pi * f * x) * np.exp(-x * 14)
        if i0 + L < N: music[i0:i0 + L] += tone * 0.05
        k += 1; x0 += beat / 2

# 장면 전환 '휙' 소리
def whoosh(tc, gain=0.18, length=0.55):
    i0 = int((tc - length * 0.6) * SR); L = int(length * SR)
    x = np.linspace(0, 1, L)
    noise = rng.standard_normal(L)
    # 단순 로우패스(이동평균)로 부드럽게
    k = 24
    noise = np.convolve(noise, np.ones(k) / k, mode="same")
    music[i0:i0 + L] += noise * np.sin(np.pi * x) ** 2 * gain * 3

for tc in [4.6, 7.65, 10.75, 13.75, 16.55]:
    whoosh(tc)

# 마지막 페이드아웃
music *= np.clip((20.0 - t) / 0.8, 0, 1)

# 기존 키보드 효과음과 합치기
with wave.open(SFX) as w:
    sfx = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2)[:, 0] / 32767
sfx = np.pad(sfx, (0, max(0, N - len(sfx))))[:N]

mix = music * 0.9 + sfx
mix = mix / max(1.0, np.abs(mix).max() / 0.89)
pcm = (np.repeat(mix[:, None], 2, axis=1) * 32767).astype(np.int16)
with wave.open(OUT, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("ok")
