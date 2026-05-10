"""SCU brand accents for Streamlit (works with `.streamlit/config.toml` theme)."""

from __future__ import annotations

import streamlit as st

# Santa Clara / brand reds referenced in product planning
SCU_RED = "#C8102E"
SCU_RED_DARK = "#8B0000"


def inject_scu_brand() -> None:
    """Apply heading and sidebar accents; primary buttons use ``config.toml`` primaryColor."""
    st.markdown(
        f"""
        <style>
            .main .block-container h1,
            .main .block-container h2,
            .main .block-container h3 {{
                color: {SCU_RED_DARK};
            }}
            section[data-testid="stSidebar"] {{
                border-left: 4px solid {SCU_RED};
                background-color: #FFF8F8 !important;
            }}
            a {{
                color: {SCU_RED} !important;
            }}
            a:hover {{
                color: {SCU_RED_DARK} !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )
