# app.py
import streamlit as st

from utils.css_styling import apply_custom_styling
from utils.qrng_helper import get_qrng_bits_from_api  # optional, used only if you want QRNG
import io, math, random, hashlib
from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from gen_art_logic import show_gen_art

st.set_page_config(layout="wide", initial_sidebar_state="expanded")
apply_custom_styling()  # safe styling (does NOT hide header/sidebar)
show_gen_art()

# ---------------------------
# Education Panel
# ---------------------------
with st.expander("What am I looking at?"):
    st.markdown(
        """
        **Chaotic Flow Field Art**  
        Each image traces thousands of particles moving through a trigonometric vector field. 
        The *field coefficients*, *start points*, and *palette* come from your chosen randomness source.

        - **QRNG** (Quantum RNG): entropy from a physical quantum process.
        - **PRNG**: algorithmic randomness from a deterministic seed.

        Try **Compare QRNG vs PRNG** to generate two images with the same parameters and visually inspect differences.  
        Use a fixed PRNG seed to make the PRNG image reproducible while the QRNG image remains uniquely unseeded.
        """
    )

with st.expander("Tips for showmanship (workshop mode)"):
    st.markdown(
        """
        - Project the app and let an audience member type their name as the PRNG seed — compare against the **QRNG** image.
        - Ask the audience to vote on their favorite; highlight that QRNG pieces are **unrepeatable**.
        - Increase **Particles** and **Steps** for denser, dreamier results (slower to render).
        - Change **Background** to white for print-style posters.
        """
    )
