# utils/css_styling.py
import streamlit as st

def apply_custom_styling():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

    html, body, p, h1, h2, h3, h4, h5, h6, label, button, .stMarkdown,
    .stTextInput, .stSelectbox, [data-baseweb="select"], [data-baseweb="textarea"], [data-baseweb="input"]{
      font-family: 'Press Start 2P', monospace !important;
    }

    html, body, [data-testid="stAppViewContainer"]{
      background-color:#0f1923;
      background-image: radial-gradient(circle at center, #1f2e3d 0%, #0f1923 100%);
      color:#fdfdfd;
    }

    /* Keep header & sidebar visible */
    header[data-testid="stHeader"]{ display:flex !important; }
    [data-testid="stSidebarCollapseButton"]{ display:inline-flex !important; }

    /* Inputs */
    input[type="text"], input[type="number"], input[type="search"], textarea{
      background:#111 !important; color:#fdfdfd !important;
      border:2px solid #ffcc00 !important; border-radius:0 !important;
      box-shadow:none !important; outline:none !important;
    }
    .stTextInput > div > input{
      background:#111 !important; color:#fdfdfd !important;
      border:2px solid #ffcc00 !important; border-radius:0 !important;
      height:44px !important; padding:10px 12px !important;
    }
    input::placeholder, textarea::placeholder{ color:#ffcc00 !important; opacity:1 !important; }
    [data-baseweb="form-control"] small{ color:#ffcc00 !important; }

    /* Select */
    [data-baseweb="select"] > div{
      background:#111 !important; color:#fdfdfd !important;
      border:2px solid #ffcc00 !important; border-radius:0 !important;
      min-height:44px !important; padding:6px 10px !important;
    }
    [data-baseweb="select"] svg{ color:#ffcc00 !important; fill:#ffcc00 !important; }

    /* Dropdown menu portal */
    [data-baseweb="menu"]{
      background:#111 !important; color:#fdfdfd !important;
      border:2px solid #ffcc00 !important; border-radius:0 !important;
    }
    [data-baseweb="menu"] [role="option"]{ color:#fdfdfd !important; padding:10px 12px !important; }
    [data-baseweb="menu"] [role="option"]:hover{ background:#232b36 !important; }

    /* Buttons */
    button[kind="primary"]{
      background:#e63946 !important; color:#fff !important; border:2px solid #fff !important;
      border-radius:0 !important;
    }
    button[kind="primary"]:hover{ background:#ff6f61 !important; color:#111 !important; }
                
    @media (max-width:768px){{
      .main-title{{ font-size:20px !important; flex-direction:column; align-items:center; text-align:center; }}
      .section-title{{ font-size:12px !important; }}
      .corner-img{{ width:90px !important; margin:0 auto 1rem auto; display:inline-block !important; }}
      .main-title-text{{ font-size:18px !important; line-height:1.4em; }}
    }}
    </style>
    """, unsafe_allow_html=True)
