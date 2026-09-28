"""Seamless procedural "oak effect" laminate textures (numpy only).

Generates tileable base colour, roughness and normal maps whose grain runs
along the texture's U axis.  Pure numpy so it runs inside Blender's bundled
Python; the build script writes the arrays to disk with bpy.

Arrays are indexed [row, col] with row 0 at the *bottom* of the image (v = 0),
matching Blender's Image.pixels layout and OpenGL-style UVs.
"""
import numpy as np

# Light natural oak, calibrated against the product photos (sRGB 0-255).
# Front-lit slats measure ~(207, 181, 156) with p10/p90 of roughly
# (195, 165, 140) / (215, 189, 165).
OAK_LIGHT = np.array([224, 200, 174], dtype=np.float64)
OAK_DARK = np.array([178, 149, 120], dtype=np.float64)


def _fft_noise(n, rng, fu, fv, power=2.0):
    """Periodic anisotropic Gaussian noise, zero mean / unit variance.

    fu / fv set the spectral roll-off (in cycles per tile) along U (columns)
    and V (rows).  A small fu with a large fv gives streaks along U.
    """
    white = rng.standard_normal((n, n))
    spec = np.fft.rfft2(white)
    kv = np.fft.fftfreq(n)[:, None] * n
    ku = np.fft.rfftfreq(n)[None, :] * n
    env = 1.0 / (1.0 + (ku / fu) ** 2 + (kv / fv) ** 2) ** (power / 2.0)
    env[0, 0] = 0.0
    out = np.fft.irfft2(spec * env, s=(n, n))
    out -= out.mean()
    out /= out.std() + 1e-12
    return out


def _ring_profile(m, rng, count):
    """Periodic 1D profile of irregular latewood lines (0 = earlywood)."""
    t = (np.arange(m) + 0.5) / m
    prof = np.zeros(m)
    for p in rng.uniform(0.0, 1.0, count):
        w = rng.uniform(0.0012, 0.0035)
        s = rng.uniform(0.35, 1.0)
        d = (t - p + 0.5) % 1.0 - 0.5
        # soft fade on the earlywood side, crisp edge on the latewood side
        prof += s * np.where(d < 0.0, np.exp(-(d / (w * 3.5)) ** 2),
                             np.exp(-(d / w) ** 2))
    return prof / (prof.max() + 1e-12)


def _sample_periodic(prof, coord):
    """Linear interpolation of a periodic 1D profile at coord in [0, 1)."""
    m = prof.shape[0]
    x = (coord % 1.0) * m - 0.5
    i0 = np.floor(x).astype(np.int64)
    f = x - i0
    return prof[i0 % m] * (1.0 - f) + prof[(i0 + 1) % m] * f


def oak_maps(n=2048, seed=7):
    """Return (base_srgb[n,n,3] 0-1, roughness[n,n] 0-1, normal[n,n,3] 0-1)."""
    rng = np.random.default_rng(seed)
    v = (np.arange(n)[:, None] + 0.5) / n
    u = (np.arange(n)[None, :] + 0.5) / n

    # Gentle waviness of the grain lines and slow drift across the board.
    warp = _fft_noise(n, rng, fu=1.2, fv=2.5, power=3.0)
    drift = 0.35 * np.sin(2.0 * np.pi * (u + 0.13)) + 0.2 * np.sin(4.0 * np.pi * (u + 0.61))
    vw = v + 0.010 * warp + 0.004 * drift

    rings = _sample_periodic(_ring_profile(8192, rng, 70), vw)
    rings_fine = _sample_periodic(_ring_profile(8192, rng, 160), vw + 0.37)

    fibres = _fft_noise(n, rng, fu=3.0, fv=180.0)          # long thin streaks
    figure = _fft_noise(n, rng, fu=0.8, fv=5.0, power=3.0)  # broad colour bands
    mottle = _fft_noise(n, rng, fu=6.0, fv=12.0, power=3.0)

    # Oak pores: short dark dashes aligned with the grain.
    pore_field = _fft_noise(n, rng, fu=40.0, fv=700.0, power=2.5)
    pores = np.clip((pore_field - 1.9) / 1.2, 0.0, 1.0)
    pores *= 0.55 + 0.45 * np.clip(rings_fine * 1.5, 0.0, 1.0)

    dark = (0.30 * rings + 0.16 * rings_fine
            + 0.07 * fibres + 0.05 * figure + 0.03 * mottle
            + 0.40 * pores)
    dark = (dark - np.percentile(dark, 1.0)) / (np.percentile(dark, 99.5) - np.percentile(dark, 1.0))
    dark = np.clip(dark, 0.0, 1.15)

    base = OAK_LIGHT[None, None, :] * (1.0 - dark[..., None]) + OAK_DARK[None, None, :] * dark[..., None]
    # a touch of warm/cool variation along the figure bands
    base[..., 0] += 2.0 * figure
    base[..., 2] -= 2.0 * figure
    base = np.clip(base / 255.0, 0.0, 1.0)

    # Satin laminate: fairly uniform sheen, pores and latewood a little rougher.
    rough = 0.50 + 0.10 * pores + 0.05 * rings + 0.02 * fibres
    rough = np.clip(rough, 0.35, 0.8)

    # Height -> tangent-space normal (OpenGL convention, +V = green up).
    height = -(0.9 * pores + 0.25 * rings + 0.08 * fibres)
    du = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dv = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    strength = 2.2
    nx, ny, nz = -du * strength, -dv * strength, np.ones_like(height)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack([nx * inv, ny * inv, nz * inv], axis=-1) * 0.5 + 0.5
    return base, rough, normal


if __name__ == "__main__":
    b, r, nm = oak_maps(512)
    print("mean sRGB", (b.reshape(-1, 3).mean(0) * 255).round(1),
          "p10", (np.percentile(b.reshape(-1, 3), 10, axis=0) * 255).round(0),
          "p90", (np.percentile(b.reshape(-1, 3), 90, axis=0) * 255).round(0),
          "rough", r.mean().round(3))
