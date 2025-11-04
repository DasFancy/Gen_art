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

def author_footer():
    st.markdown(
        """
        <hr style="border-top: 1px dashed #999;">
        <div style='text-align: center; font-family: "Press Start 2P", monospace; color: #888888; font-size: 14px; margin-top: 2rem;'>
            Brewed by <a href="https://cn.ifn.et.tu-dresden.de/chair/staff/m-sc-siddharth-das" target="_blank" style="color: #FFD700; text-decoration: none;">Sid</a><br>
            <span style="font-size: 16px;">Want to jam on randomness? Let's connect.</span>
        </div>
        """,
        unsafe_allow_html=True
    )


st.set_page_config(layout="wide", initial_sidebar_state="expanded")
st.title('Generative Art')
apply_custom_styling()  # safe styling (does NOT hide header/sidebar)
st.markdown("""
<style>
/* Try to force BaseWeb slider value label to be visible */
[data-baseweb="slider"] [aria-hidden="true"] {
  opacity: 1 !important;
  visibility: visible !important;
  transform: none !important;
}

/* Also make the tick bar labels (if present) fully visible */
[data-baseweb="slider"] [data-baseweb="tick"] * {
  opacity: 1 !important;
  visibility: visible !important;
}
</style>
""", unsafe_allow_html=True)

show_gen_art()

# ---------------------------
# Education Panel
# ---------------------------
st.markdown("""
<style>
.push-to-bottom {
    flex-grow: 1 !important;
    height: 100%;
}
</style>
<div class="push-to-bottom"></div>
""", unsafe_allow_html=True)
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
    , unsafe_allow_html = True)

author_footer()