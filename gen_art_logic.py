import hashlib
import streamlit as st
import io
import math, random
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import requests
from utils.qrng_helper import get_qrng_bits_from_api
from utils.css_styling import apply_custom_styling


# ---------------------------
# Randomness Providers
# ---------------------------

def show_gen_art():
    
    
    class RandomnessProvider:
        def get_bytes(self, n: int) -> bytes:
            raise NotImplementedError

        def get_uint32(self, k: int) -> np.ndarray:
            """Return k unsigned 32-bit integers."""
            raw = self.get_bytes(4 * k)
            return np.frombuffer(raw, dtype=np.uint32, count=k)

        def get_floats(self, k: int) -> np.ndarray:
            """Return k floats in [0,1)."""
            # Map uint32 to [0,1)
            u = self.get_uint32(k).astype(np.float64)
            return (u / np.float64(2**32))

    class PRNGProvider(RandomnessProvider):
        def __init__(self, seed: Optional[int] = None):
            # PCG64 is a high-quality PRNG
            self.rng = np.random.default_rng(seed)

        def get_bytes(self, n: int) -> bytes:
            return self.rng.integers(0, 256, size=n, dtype=np.uint8).tobytes()


    def get_qrng_bytes(n_bytes: int) -> bytes:
        n_bits = n_bytes * 8
        bitstring = get_qrng_bits_from_api(n_bits)
        # Convert bitstring -> integer -> bytes
        return int(bitstring, 2).to_bytes(n_bytes, "big")


    class QRNGProvider(RandomnessProvider):
        def get_bytes(self, n: int) -> bytes:
            return get_qrng_bytes(n)
    # ---------------------------
    # Utility: Palette & Hashing
    # ---------------------------

    def bytes_to_seed(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()


    def seed_to_int(seed_hex: str) -> int:
        return int(seed_hex[:16], 16)


    def hsl_to_rgb(h: float, s: float, l: float) -> Tuple[int, int, int]:
        # h in [0, 360), s,l in [0,1]
        c = (1 - abs(2*l - 1)) * s
        hp = (h % 360) / 60.0
        x = c * (1 - abs(hp % 2 - 1))
        r1 = g1 = b1 = 0
        if   0 <= hp < 1: r1, g1, b1 = c, x, 0
        elif 1 <= hp < 2: r1, g1, b1 = x, c, 0
        elif 2 <= hp < 3: r1, g1, b1 = 0, c, x
        elif 3 <= hp < 4: r1, g1, b1 = 0, x, c
        elif 4 <= hp < 5: r1, g1, b1 = x, 0, c
        elif 5 <= hp < 6: r1, g1, b1 = c, 0, x
        m = l - c/2
        r, g, b = (r1 + m), (g1 + m), (b1 + m)
        return int(255*r), int(255*g), int(255*b)


    def palette_from_bytes(b: bytes, n_colors: int, vivid: bool = True) -> List[Tuple[int, int, int]]:
        """Derive a palette from random bytes via SHA256 blocks."""
        if len(b) < 32:
            b = hashlib.sha256(b).digest()
        colors = []
        offset = 0
        while len(colors) < n_colors:
            block = hashlib.sha256(b[offset:offset+32]).digest()
            h = int.from_bytes(block[0:2], 'big') % 360
            s = 0.65 if vivid else 0.45
            l = 0.58 if vivid else 0.5
            colors.append(hsl_to_rgb(h, s, l))
            offset = (offset + 7) % len(b)
        return colors

    # ---------------------------
    # Generative Engine: Chaotic Flow Field
    # ---------------------------

    @dataclass
    class FlowFieldParams:
        width: int = 1600
        height: int = 1000
        particles: int = 18000
        steps: int = 80
        step_size: float = 0.9
        jitter: float = 0.4
        line_alpha: int = 20  # 0..255
        bg_color: Tuple[int, int, int] = (10, 10, 10)


    def make_coeffs(r: RandomnessProvider, k: int = 8) -> np.ndarray:
        # Generate Kx6 coefficients for trig field from QRNG/PRNG
        vals = r.get_floats(k * 6).reshape(k, 6)
        # Scale ranges to create diverse fields
        scales = np.array([3.5, 3.5, 2.0, 3.5, 3.5, 2.0])
        return vals * scales


    def vec_field(x: np.ndarray, y: np.ndarray, C: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        # C shape: (K,6) with (ax, bx, cx, ay, by, cy)
        # Build a rich field by summing sin/cos terms
        u = np.zeros_like(x)
        v = np.zeros_like(y)
        for (ax, bx, cx, ay, by, cy) in C:
            u += np.sin(ax * x + bx * y + cx)
            v += np.cos(ay * x + by * y + cy)
        return u, v


    def render_flow_field(r: RandomnessProvider, p: FlowFieldParams, palette: List[Tuple[int, int, int]], coeffs=None) -> Image.Image:
        progress = st.progress(0)

        W, H = p.width, p.height
        img = Image.new("RGBA", (W, H), p.bg_color + (255,))
        draw = ImageDraw.Draw(img, 'RGBA')

        # Coefficients for field
        C = coeffs if coeffs is not None else make_coeffs(r, 8)

        # Initialize particles
        # Start points drawn from low-discrepancy-like sampling via random hashing
        raw = r.get_bytes(8 * p.particles)
        arr = np.frombuffer(raw, dtype=np.uint16, count=p.particles*4)
        arr = arr.reshape(p.particles, 4).astype(np.float64)
        xs = (arr[:,0] / 65535.0) * W
        ys = (arr[:,1] / 65535.0) * H

        jitter = (arr[:,2] / 65535.0) * p.jitter
        col_idx = (arr[:,3] % len(palette)).astype(np.int32)

        # Normalize coords for vector field domain
        x = xs / W * 2 * math.pi
        y = ys / H * 2 * math.pi

        for step in range(p.steps):
            u, v = vec_field(x, y, C)
            # Normalize vectors to unit length, avoid division by zero
            mag = np.sqrt(u*u + v*v) + 1e-8
            u /= mag
            v /= mag

            # Advance positions in pixel space
            xs += (u * p.step_size + (np.random.rand(p.particles) - 0.5) * jitter)
            ys += (v * p.step_size + (np.random.rand(p.particles) - 0.5) * jitter)

            # Clip to bounds
            mask = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
            if not np.any(mask):
                break

            # Draw visible subset (masked)
            xs_m = xs[mask]
            ys_m = ys[mask]
            cols = np.array(palette, dtype=np.uint8)[col_idx[mask]]

            # Draw one point per particle with its OWN palette color.
            # Keeps PIL's alpha-compositing buildup (the layered density look).
            alpha = p.line_alpha
            for px, py, (r_, g_, b_) in zip(xs_m, ys_m, cols):
                draw.point((int(px), int(py)), fill=(int(r_), int(g_), int(b_), alpha))

            # Update field coords
            x = xs / W * 2 * math.pi
            y = ys / H * 2 * math.pi
            progress.progress((step+1)/p.steps)

        return img

    def overlay_stars(img: Image.Image, r: RandomnessProvider, n_stars: int = 200) -> Image.Image:
        """Add scattered glowing stars."""
        draw = ImageDraw.Draw(img, 'RGBA')
        raw = r.get_bytes(n_stars * 4)
        arr = np.frombuffer(raw, dtype=np.uint16, count=n_stars*2).reshape(n_stars, 2)
        W, H = img.size
        for x, y in arr:
            px, py = int((x/65535)*W), int((y/65535)*H)
            size = np.random.randint(2, 6)
            color = (255, 255, 200, np.random.randint(120, 200))
            draw.ellipse((px-size, py-size, px+size, py+size), fill=color)
        return img

    def overlay_texture(img: Image.Image) -> Image.Image:
        """Apply a subtle canvas texture effect."""
        # Downsample + upsample with a slight blur to simulate grain
        tex = img.copy().filter(ImageFilter.GaussianBlur(0.6))
        return Image.blend(img, tex, 0.15)

    def overlay_vangogh(img, r: RandomnessProvider, flow_coeffs, n_strokes=600):
        """Overlay Van Gogh–like brush strokes aligned with flow field, avoiding confetti look."""
        W, H = img.size
        draw = ImageDraw.Draw(img, 'RGBA')

        # limit palette to 3 main colors
        base_palette = palette_from_bytes(r.get_bytes(256), 8)
        main_palette = random.sample(base_palette, 3)

        raw = r.get_bytes(n_strokes * 8)
        arr = np.frombuffer(raw, dtype=np.uint16, count=n_strokes*4).reshape(n_strokes, 4)

        for (x, y, w, h) in arr:
            px, py = int((x/65535)*W), int((y/65535)*H)

            # flow direction
            u, v = vec_field(
                np.array([px/W*2*math.pi]),
                np.array([py/H*2*math.pi]),
                flow_coeffs
            )
            angle = math.atan2(v[0], u[0])

            # choose one of the restricted palette colors
            color = random.choice(main_palette)
            jitter = np.random.randint(-20, 20)
            stroke_color = (
                min(255, max(0, color[0] + jitter)),
                min(255, max(0, color[1] + jitter)),
                min(255, max(0, color[2] + jitter)),
                np.random.randint(160, 220)
            )

            # bigger strokes
            length = 20 + (w/65535)*40
            width = 6 + (h/65535)*8

            # # stroke as rotated oval
            # stroke = Image.new("RGBA", img.size, (0,0,0,0))
            # stroke_draw = ImageDraw.Draw(stroke)
            # bbox = [px - length//2, py - width//2, px + length//2, py + width//2]
            # stroke_draw.ellipse(bbox, fill=stroke_color)
            # img.alpha_composite(stroke.rotate(math.degrees(angle), center=(px, py)))

        return img

    def overlay_scene(img: Image.Image, r: RandomnessProvider, coeffs, n_strokes=1200) -> Image.Image:
        """Render a scenic landscape with split mountains and central shimmering water reflection."""

        W, H = img.size
        draw = ImageDraw.Draw(img, 'RGBA')

        # --- Helper for brightness contrast ---
        def enforce_contrast(c1, c2, threshold=60):
            l1 = 0.2126*c1[0] + 0.7152*c1[1] + 0.0722*c1[2]
            l2 = 0.2126*c2[0] + 0.7152*c2[1] + 0.0722*c2[2]
            return abs(l1 - l2) > threshold

        # --- Generate base palette ---
        base_palette = palette_from_bytes(r.get_bytes(512), 8)
        sky_color = random.choice(base_palette)
        mountain_color = random.choice(base_palette)
        water_color = (50, 100, 180)

        # Ensure contrast between sky and mountain
        attempts = 0
        while not enforce_contrast(sky_color, mountain_color) and attempts < 10:
            mountain_color = random.choice(base_palette)
            attempts += 1

        # --- Draw gradient sky ---
        top_color = (max(0, sky_color[0]-20), max(0, sky_color[1]-20), min(255, sky_color[2]+40))
        for y in range(H//2):
            blend = y / (H//2)
            r_ = int(top_color[0]*(1-blend) + sky_color[0]*blend)
            g_ = int(top_color[1]*(1-blend) + sky_color[1]*blend)
            b_ = int(top_color[2]*(1-blend) + sky_color[2]*blend)
            draw.line((0, y, W, y), fill=(r_, g_, b_, 255))

        # --- Water base ---
        draw.rectangle([0, H//2, W, H], fill=water_color + (255,))

        # # --- Split mountains ---
        # def make_mountain(x_start, x_end, height_factor, roughness=30):
        #     points = []
        #     xs = list(range(x_start, x_end, 40))
        #     noise = np.frombuffer(r.get_bytes(len(xs)*2), dtype=np.uint16)
        #     noise = (noise / 65535.0 - 0.5) * roughness
        #     for i, x in enumerate(xs):
        #         peak = H * height_factor
        #         offset = noise[i % len(noise)]
        #         y = int(peak + 25 * math.sin(x / 120.0) + offset)
        #         points.append((x, y))
        #     points.append((x_end, H))
        #     points.append((x_start, H))
        #     return points

        # left_mountain = make_mountain(0, int(W * 0.4), 0.55)
        # right_mountain = make_mountain(int(W * 0.6), W, 0.55)

        # draw.polygon(left_mountain, fill=mountain_color + (255,))
        # draw.polygon(right_mountain, fill=mountain_color + (255,))

        # --- Sun ---
        cx, cy, radius = W // 2, int(H * 0.32), int(H * 0.1)
        sun_color = (255, 220, 100)
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=sun_color + (255,)
        )

        # --- Shimmer reflection down the center ---
        shimmer_count = 120
        for _ in range(shimmer_count):
            offset = np.random.uniform(-radius * 0.5, radius * 0.5)
            length = np.random.randint(10, 60)
            y = np.random.randint(int(H * 0.55), H - 5)
            alpha = np.random.randint(60, 120)
            draw.line(
                (cx + offset, y, cx + offset + length, y),
                fill=(255, 240, 190, alpha),
                width=np.random.randint(1, 2)
            )

        # --- Gentle water ripples ---
        for _ in range(n_strokes // 8):
            px, py = np.random.randint(0, W), np.random.randint(int(H * 0.55), H)
            alpha = np.random.randint(20, 60)
            draw.line((px, py, px + 4, py), fill=(255, 255, 255, alpha), width=1)

        return img

    with st.sidebar:
        
        st.header("Controls")
        width = st.number_input("Width", 512, 4096, 1600, step=64)
        height = st.number_input("Height", 512, 4096, 1000, step=64)
        particles = st.slider("Particles", 1000, 50000, 18000, step=1000)
        steps = st.slider("Steps per particle", 20, 300, 80, step=5)
        step_size = st.slider("Step size", 0.1, 3.0, 0.9, step=0.1)
        jitter = st.slider("Jitter", 0.0, 2.0, 0.4, step=0.05)
        line_alpha = st.slider("Stroke alpha", 5, 80, 20)
        vivid = st.toggle("Vivid palette", value=True)

        st.markdown("---")
        st.subheader("Randomness Source")
        mode = st.radio("Source", ["QRNG", "PRNG", "Compare QRNG vs PRNG"], index=0)
        prng_seed_text = st.text_input("PRNG seed (optional)")

        st.markdown("---")
        bg_color = st.color_picker("Background", value="#0a0a0a")
        bg_tuple = tuple(int(bg_color[i:i+2], 16) for i in (1,3,5))

        st.markdown("---")
        st.subheader("Overlays")

        st.markdown("""
            <style>
            [data-baseweb="select"] { display: block !important; visibility: visible !important; }
            [data-baseweb="select"] > div { background:#111 !important; }
            [data-baseweb="menu"] { background:#111 !important; }

            /* Stop clipping option text in the overlay select */
            [data-baseweb="select"] > div,
            [data-baseweb="menu"] [role="option"]{
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            line-height: 1.6em !important;
            }
            /* Shrink just the select/menu font so long labels fit */
            [data-baseweb="select"], [data-baseweb="menu"]{
            font-size: 9px !important;
            }
            </style>
        """, unsafe_allow_html=True)

        overlay = st.selectbox("Choose overlay", ["None", "Stars", "Grain", "VanGogh", "Scene"], index=0, key="overlay_select")

        generate = st.button("✨ Generate Art", type="primary")
        surprise = st.button("🎲 Surprise Me")

    # Pack params
    params = FlowFieldParams(
        width=int(width),
        height=int(height),
        particles=int(particles),
        steps=int(steps),
        step_size=float(step_size),
        jitter=float(jitter),
        line_alpha=int(line_alpha),
        bg_color=bg_tuple,
    )

    # Helper to make one image from a provider

    def make_image_with_provider(provider: RandomnessProvider, label: str, overlay: str) -> Tuple[Image.Image, str, List[Tuple[int,int,int]], np.ndarray]:
        # Seed bytes for palette + provenance record
        seed_bytes = provider.get_bytes(4096)
        seed_hex = bytes_to_seed(seed_bytes)
        palette = palette_from_bytes(seed_bytes, n_colors=10, vivid=vivid)
        coeffs = make_coeffs(provider, 8)

        if overlay == "Scene":
            # start with a plain background
            img = Image.new("RGBA", (params.width, params.height), params.bg_color + (255,))
        else:
            # normal chaotic flow
            img = render_flow_field(provider, params, palette, coeffs=coeffs)

        return img, seed_hex, palette, coeffs

    # Build providers
    qrng_provider = None
    if mode in ("QRNG", "Compare QRNG vs PRNG"):
        qrng_provider = QRNGProvider()

    prng_seed = None
    if prng_seed_text.strip():
        try:
            prng_seed = int(prng_seed_text.strip(), 0)
        except ValueError:
            prng_seed = int(hashlib.sha256(prng_seed_text.encode()).hexdigest()[:16], 16)

    prng_provider = PRNGProvider(seed=prng_seed)
    #------------------------------Surprise addition ---------------------------------------------------------
    if surprise:
        params.particles = random.choice([12000, 18000, 26000, 35000])
        params.steps     = random.choice([60, 80, 120, 160])
        params.step_size = random.choice([0.6, 0.9, 1.2, 1.6])
        params.jitter    = random.choice([0.2, 0.4, 0.7, 1.0])
        params.line_alpha = random.choice([12, 20, 30, 45])
        overlay = random.choice(["None", "Stars", "Texture", "Van Gogh", "Scene"])
        generate = True   # reuse the existing generation path

    if generate:
        if mode == "QRNG" and not qrng_provider:
            st.error("Please provide a valid QRNG base URL (http/https).")
        else:
            if mode == "Compare QRNG vs PRNG":
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("QRNG")
                    try:
                        with st.spinner("Painting in progress ... please wait"):
                            img_q, seed_q, pal_q, coeffs = make_image_with_provider(qrng_provider, "QRNG", overlay)
                            if overlay == "Stars":
                                img_q = overlay_stars(img_q, qrng_provider)
                            elif overlay == "Texture":
                                img_q = overlay_texture(img_q)
                            elif overlay == "Van Gogh":
                                img_q = overlay_vangogh(img_q, qrng_provider, coeffs)
                            elif overlay == "Scene":
                                img_q = overlay_scene(img_q, qrng_provider, coeffs)
                        bio_q = io.BytesIO()
                        img_q = img_q.convert("RGB")
                        img_q.save(bio_q, format="PNG")
                        st.image(img_q, caption=f"Seed: {seed_q[:16]}… (SHA-256)")
                        st.download_button("Download QRNG PNG", data=bio_q.getvalue(), file_name=f"qrng_art_{seed_q[:12]}.png", mime="image/png")
                    except Exception as e:
                        st.exception(e)
                with col2:
                    st.subheader("PRNG")
                    with st.spinner("Painting in progress ... please wait"):
                        img_p, seed_p, pal_p, coeffs = make_image_with_provider(prng_provider, "PRNG", overlay)
                        if overlay == "Stars":
                            img_p = overlay_stars(img_p, prng_provider)
                        elif overlay == "Texture":
                            img_p = overlay_texture(img_p)
                        elif overlay == "Van Gogh":
                            img_p = overlay_vangogh(img_p, prng_provider, coeffs)
                        elif overlay == "Scene":
                            img_p = overlay_scene(img_p, prng_provider, coeffs)
        
                    bio_p = io.BytesIO()
                    img_p = img_p.convert("RGB")
                    img_p.save(bio_p, format="PNG")
                    st.image(img_p, caption=f"Seed: {seed_p[:16]}… (SHA-256)")
                    st.download_button("Download PRNG PNG", data=bio_p.getvalue(), file_name=f"prng_art_{seed_p[:12]}.png", mime="image/png")
            else:
                provider = qrng_provider if mode == "QRNG" else prng_provider
                with st.spinner("Painting in progress ... please wait"):
                    img, seed_hex, pal, coeffs = make_image_with_provider(provider, mode, overlay)
                    if overlay == "Stars":
                        img = overlay_stars(img, provider)
                    elif overlay == "Texture":
                        img = overlay_texture(img)
                    elif overlay == "Van Gogh":
                        img = overlay_vangogh(img, provider, coeffs)
                    elif overlay == "Scene":
                            img = overlay_scene(img, provider, coeffs)
                bio = io.BytesIO()
                img = img.convert("RGB")
                img.save(bio, format="PNG")
                st.image(img, caption=f"Seed: {seed_hex[:16]}… (SHA-256)")
                st.download_button("Download PNG", data=bio.getvalue(), file_name=f"{mode.lower()}_art_{seed_hex[:12]}.png", mime="image/png")


