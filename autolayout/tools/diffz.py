"""diffz.py - tinh tro khang duong truyen tu stackup bang giai truong 2D (sai phan huu han + CG, numpy) (L77).

Mat cat: mat GND day o y=0 (lop duoi), dien moi h/er, tren cung: 1 hoac 2 day rong w, cach nhau s;
GND pour cung lop cach mep day g (g=0 -> khong co pour: microstrip thuong). Bo qua solder mask (lam Z thap hon ~1-3 ohm).

  diffz.py selftest                                   : so voi cong thuc Hammerstad (microstrip don) de kiem bo giai
  diffz.py z    --w W --s S --g G [--h 1.51 --er 4.5 --t 0.035]     : Zdiff, Zodd, Zeven, Z0 (1 day)
  diffz.py find --s S --g G [--target 100] [...]      : tim w cho Zdiff = target (chia doi)
Don vi mm, ohm.
"""
import math
import sys

import numpy as np

C0 = 299792458.0
E0 = 8.8541878128e-12


def solve(w, s, g, h, er, t, mode, diel=True, dx=0.025, air=6.0, side=6.0):   # vo 6 mm: hoi tu (selftest: -3% so Hammerstad o vo 10 mm)
    """mode 'odd' (+1/-1), 'even' (+1/+1), 'single' (1 day). Tra ve C (F/m) moi day."""
    pair = mode != "single"
    span = (2 * w + s) if pair else w
    gp = g if g > 0 else 0
    W = span + 2 * (gp + side); H = h + t + air
    nx, ny = int(round(W / dx)) + 1, int(round(H / dx)) + 1
    jh, jt = int(round(h / dx)), max(1, int(round(t / dx)))
    eps = np.ones((ny, nx))
    if diel:
        eps[:jh, :] = er; eps[jh, :] = (er + 1) / 2
    fixed = np.zeros((ny, nx), bool); phi = np.zeros((ny, nx))
    fixed[0, :] = fixed[-1, :] = True; fixed[:, 0] = fixed[:, -1] = True          # GND duoi + vo xa = 0
    x0 = (W - span) / 2
    strips = [(x0, x0 + w, 1.0)] + ([(x0 + w + s, x0 + 2 * w + s, -1.0 if mode == "odd" else 1.0)] if pair else [])
    rows = slice(jh, jh + jt + 1)
    for a, b, v in strips:
        ia, ib = int(round(a / dx)), int(round(b / dx))
        fixed[rows, ia:ib + 1] = True; phi[rows, ia:ib + 1] = v
    if g > 0:                                                                       # pour 2 ben, noi dat
        ia, ib = int(round((x0 - g) / dx)), int(round((x0 + span + g) / dx))
        fixed[rows, :ia + 1] = True; fixed[rows, ib:] = True
    # he so canh (eps trung binh 2 nut)
    ex = (eps[:, 1:] + eps[:, :-1]) / 2; ey = (eps[1:, :] + eps[:-1, :]) / 2
    free = ~fixed

    def A(u):                                    # -div(eps grad u) tren nut tu do, u = 0 tai nut co dinh
        r = np.zeros_like(u)
        fx = ex * (u[:, 1:] - u[:, :-1]); fy = ey * (u[1:, :] - u[:-1, :])
        r[:, :-1] -= fx; r[:, 1:] += fx; r[:-1, :] -= fy; r[1:, :] += fy
        return np.where(free, r, 0.0)
    b = -np.where(free, _apply_full(np.where(fixed, phi, 0.0), ex, ey), 0.0)      # ve phai tu dien the cua vat dan
    x = np.zeros_like(phi); r = b - A(x); p = r.copy(); rs = (r * r).sum()
    for _ in range(20000):
        Ap = A(p); al = rs / (p * Ap).sum(); x += al * p; r -= al * Ap; rn = (r * r).sum()
        if rn < 1e-20 * max(1.0, (b * b).sum()):
            break
        p = r + rn / rs * p; rs = rn
    u = np.where(fixed, phi, x)
    en = 0.5 * ((ex * (u[:, 1:] - u[:, :-1]) ** 2).sum() + (ey * (u[1:, :] - u[:-1, :]) ** 2).sum())   # *E0, dx/dx = 1
    E = en * E0
    return E if pair else 2 * E      # odd/even: E = 0.5*(C*1^2 + C*1^2) = C moi day ; 1 day: E = 0.5*C


def _apply_full(u, ex, ey):
    r = np.zeros_like(u)
    fx = ex * (u[:, 1:] - u[:, :-1]); fy = ey * (u[1:, :] - u[:-1, :])
    r[:, :-1] -= fx; r[:, 1:] += fx; r[:-1, :] -= fy; r[1:, :] += fy
    return r


def Z(w, s, g, h=1.51, er=4.5, t=0.035, mode="odd"):
    c = solve(w, s, g, h, er, t, mode, True); ca = solve(w, s, g, h, er, t, mode, False)
    return 1 / (C0 * math.sqrt(c * ca)), c / ca


def hammerstad(w, h, er):
    u = w / h; ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
    z = 120 * math.pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444))) if u >= 1 else 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    return z


def arg(k, d):
    a = sys.argv
    return float(a[a.index(k) + 1]) if k in a else d


if __name__ == "__main__":
    cmd = sys.argv[1]
    h, er, t = arg("--h", 1.51), arg("--er", 4.5), arg("--t", 0.035)
    if cmd == "selftest":
        for w in (0.5, 1.5, 2.9):
            z, ee = Z(w, 0, 0, h, er, 0.001, "single"); zr = hammerstad(w, h, er)
            print(f"microstrip w={w}: giai {z:.1f} ohm  | Hammerstad {zr:.1f} ohm  | lech {100 * (z - zr) / zr:+.1f}%")
    elif cmd == "z":
        w, s, g = arg("--w", 0.3), arg("--s", 0.15), arg("--g", 0.2)
        zo, eo = Z(w, s, g, h, er, t, "odd"); ze, _ = Z(w, s, g, h, er, t, "even")
        print(f"w={w} s={s} g={g} h={h} er={er}: Zdiff={2 * zo:.1f}  Zodd={zo:.1f}  Zeven={ze:.1f}  Zcm={ze / 2:.1f}  eeff_odd={eo:.2f}")
    elif cmd == "find":
        s, g, tg = arg("--s", 0.15), arg("--g", 0.2), arg("--target", 100.0)
        lo, hi = 0.1, 3.0
        for _ in range(14):
            m = (lo + hi) / 2; zd = 2 * Z(m, s, g, h, er, t, "odd")[0]
            lo, hi = (m, hi) if zd > tg else (lo, m)
        m = round((lo + hi) / 2, 3); zd = 2 * Z(m, s, g, h, er, t, "odd")[0]
        print(f"s={s} g={g}: w={m} mm -> Zdiff={zd:.1f} ohm (target {tg})")
