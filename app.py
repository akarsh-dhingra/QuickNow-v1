"""QuickMind — AI Shopping Agent (Streamlit frontend).

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

import config
from agent.bedrock_agent import run_agent
from db import memory
from models.cart import Cart

st.set_page_config(
    page_title="QuickMind — AI Shopping Agent",
    layout="wide",
    page_icon="🛒",
)


# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
:root {
    --amz-orange: #FF9900;
    --amz-dark: #131921;
    --amz-gray: #666666;
}
.qm-header {
    background: var(--amz-dark);
    padding: 14px 24px;
    border-radius: 10px;
    margin-bottom: 18px;
}
.qm-header .logo {
    color: var(--amz-orange);
    font-size: 28px;
    font-weight: 800;
    letter-spacing: 0.5px;
}
.qm-header .sub {
    color: #DDDDDD;
    font-size: 13px;
}
.qm-logo-big {
    color: var(--amz-orange);
    font-size: 40px;
    font-weight: 800;
    margin-bottom: 0;
}
.qm-tagline {
    color: var(--amz-gray);
    font-style: italic;
    font-size: 15px;
    margin-top: -4px;
}
.qm-budget {
    color: var(--amz-orange);
    font-weight: 800;
    font-size: 22px;
}
/* Primary buttons -> Amazon orange */
.stButton > button[kind="primary"],
div[data-testid="stButton"] > button[kind="primary"] {
    background-color: var(--amz-orange);
    color: #FFFFFF;
    font-weight: 700;
    border: none;
    border-radius: 8px;
}
.stButton > button[kind="primary"]:hover {
    background-color: #e88b00;
    color: #FFFFFF;
}
/* Slider thumb / track in orange */
div[data-baseweb="slider"] div[role="slider"] {
    background-color: var(--amz-orange) !important;
}
.qm-card {
    background: #FFFFFF;
    border: 1px solid #E3E6E6;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.qm-item-name { font-weight: 700; font-size: 16px; }
.qm-line-total { color: var(--amz-orange); font-weight: 800; font-size: 16px; text-align: right; }
.qm-unit { color: var(--amz-gray); font-size: 13px; }
.qm-pill {
    background: #F0F2F2;
    color: var(--amz-gray);
    font-size: 11px;
    padding: 2px 10px;
    border-radius: 999px;
    margin-left: 6px;
}
.qm-just {
    color: var(--amz-gray);
    font-style: italic;
    font-size: 12px;
    margin-top: 6px;
}
.qm-placeholder {
    text-align: center;
    color: var(--amz-gray);
    padding: 60px 20px;
}
.qm-placeholder .emoji { font-size: 64px; }
.qm-remaining-green { color: #007600; font-weight: 700; }
.qm-remaining-red { color: #B12704; font-weight: 700; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state() -> None:
    st.session_state.setdefault("cart", None)
    st.session_state.setdefault("loading", False)
    st.session_state.setdefault("user_id", config.DEFAULT_USER_ID)
    st.session_state.setdefault("conversation_history", [])
    st.session_state.setdefault("intent_text", "")
    st.session_state.setdefault("budget", 500)
    st.session_state.setdefault("pending_build", False)
    st.session_state.setdefault("error", None)


_init_state()


def _get_cart() -> Cart | None:
    raw = st.session_state.get("cart")
    if raw is None:
        return None
    return Cart.from_dict(raw)


def _store_cart(cart: Cart | None) -> None:
    st.session_state.cart = cart.to_dict() if cart is not None else None


# ---------------------------------------------------------------------------
# Agent invocation helpers
# ---------------------------------------------------------------------------
def _build_cart_action(intent: str, budget: float) -> None:
    """Run the agent to build a brand-new cart."""
    st.session_state.error = None
    spinner_msgs = (
        "🧠 Understanding your intent...  🔍 Searching 50,000+ products...  "
        "⚖️ Optimising for your budget...  🛒 Building your cart..."
    )
    try:
        with st.spinner(spinner_msgs):
            cart = run_agent(
                user_intent=intent,
                budget=float(budget),
                user_id=st.session_state.user_id,
            )
        _store_cart(cart)
        st.session_state.conversation_history.append(
            {"role": "user", "intent": intent, "budget": budget}
        )
    except Exception as exc:  # noqa: BLE001
        st.session_state.error = str(exc)


def _update_cart_action(change_request: str) -> None:
    """Run the agent in change-loop mode against the existing cart."""
    st.session_state.error = None
    cart = _get_cart()
    if cart is None:
        return
    try:
        with st.spinner("🔄 Updating your cart..."):
            new_cart = run_agent(
                user_intent=cart.intent,
                budget=cart.budget,
                user_id=st.session_state.user_id,
                cart_state=cart.to_dict(),
                change_request=change_request,
            )
        _store_cart(new_cart)
        st.session_state.conversation_history.append(
            {"role": "user", "change": change_request}
        )
    except Exception as exc:  # noqa: BLE001
        st.session_state.error = str(exc)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="qm-header">'
    '<span class="logo">🛒 QuickMind</span>'
    '&nbsp;&nbsp;<span class="sub">Amazon Now · Intent-driven quick commerce</span>'
    "</div>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Handle a pending build triggered by example chips (runs before widgets draw)
# ---------------------------------------------------------------------------
if st.session_state.pending_build:
    st.session_state.pending_build = False
    _build_cart_action(
        st.session_state.intent_text, st.session_state.budget
    )


left, right = st.columns([1, 2], gap="large")


# ---------------------------------------------------------------------------
# LEFT COLUMN — inputs
# ---------------------------------------------------------------------------
with left:
    st.markdown('<p class="qm-logo-big">🛒 QuickMind</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="qm-tagline">Tell us what you need. We\'ll handle the rest.</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    intent = st.text_area(
        "What do you need today?",
        value=st.session_state.intent_text,
        height=100,
        key="intent_input",
        placeholder=(
            "e.g., Quick dinner for 4 people\n"
            "e.g., Birthday party snacks\n"
            "e.g., Weekly breakfast essentials"
        ),
    )

    budget = st.slider(
        "Budget (₹)",
        min_value=50,
        max_value=2000,
        value=int(st.session_state.budget),
        step=50,
        key="budget_slider",
    )
    st.session_state.budget = budget
    st.markdown(
        f'<span class="qm-budget">₹{budget}</span>', unsafe_allow_html=True
    )

    if st.button("✨ Build My Cart", type="primary", use_container_width=True):
        st.session_state.intent_text = intent
        if intent and intent.strip():
            _build_cart_action(intent.strip(), budget)
        else:
            st.session_state.error = "Please describe what you need first."

    st.divider()
    st.caption("Try an example:")

    chip1, chip2, chip3 = st.columns(3)

    def _trigger_example(text: str, amount: int) -> None:
        st.session_state.intent_text = text
        st.session_state.budget = amount
        st.session_state.pending_build = True

    with chip1:
        if st.button("🍽️ Dinner for 4, ₹500", use_container_width=True):
            _trigger_example("Quick dinner for 4 people", 500)
            st.rerun()
    with chip2:
        if st.button("🎂 Birthday party, ₹1000", use_container_width=True):
            _trigger_example("Birthday party snacks and drinks", 1000)
            st.rerun()
    with chip3:
        if st.button("🌅 Quick breakfast, ₹200", use_container_width=True):
            _trigger_example("Quick breakfast essentials", 200)
            st.rerun()


# ---------------------------------------------------------------------------
# RIGHT COLUMN — cart display
# ---------------------------------------------------------------------------
with right:
    if st.session_state.error:
        st.error(
            f"Something went wrong: {st.session_state.error}\nPlease try again."
        )

    cart = _get_cart()

    if cart is None:
        st.markdown(
            '<div class="qm-placeholder">'
            '<div class="emoji">🛒</div>'
            "<h3>Your cart will appear here</h3>"
            "<p>Describe what you need on the left and click "
            "<b>Build My Cart</b></p>"
            '<p style="font-size:13px;">🍽️ Dinner for 4 &nbsp;•&nbsp; '
            "🎂 Birthday party &nbsp;•&nbsp; 🌅 Breakfast essentials</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        total = cart.total
        bud = cart.budget
        remaining = cart.remaining_budget

        st.subheader(
            f"🛒 Your Cart — {len(cart.items)} items — "
            f"₹{total:.0f} / ₹{bud:.0f}"
        )

        progress = min(total / bud, 1.0) if bud > 0 else 0.0
        st.progress(progress)

        if remaining > 0:
            st.markdown(
                f'<span class="qm-remaining-green">₹{remaining:.0f} remaining'
                "</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span class="qm-remaining-red">₹{remaining:.0f} remaining'
                "</span>",
                unsafe_allow_html=True,
            )

        st.write("")

        for item in cart.items:
            with st.container(border=True):
                top_l, top_r = st.columns([4, 1])
                with top_l:
                    st.markdown(
                        f'<span class="qm-item-name">{item.product.name}</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<span class="qm-unit">{item.product.unit} '
                        f"&nbsp;×&nbsp; {item.quantity}</span>"
                        f'<span class="qm-pill">{item.product.category}</span>',
                        unsafe_allow_html=True,
                    )
                with top_r:
                    st.markdown(
                        f'<span class="qm-line-total">₹{item.line_total:.0f}'
                        "</span>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "✕",
                        key=f"rm_{item.product.product_id}",
                        help="Remove item",
                    ):
                        cart.remove_item(item.product.product_id)
                        _store_cart(cart)
                        st.rerun()
                st.markdown(
                    f'<div class="qm-just">💡 {item.justification}</div>',
                    unsafe_allow_html=True,
                )

        st.divider()

        # --- Change request area ------------------------------------------
        change_request = st.text_input(
            "Refine your cart...",
            key="change_input",
            placeholder=(
                "e.g., Remove dairy  •  Add something for dessert  •  "
                "Swap paneer for tofu"
            ),
        )
        if st.button("↺ Update Cart", use_container_width=True):
            if change_request and change_request.strip():
                _update_cart_action(change_request.strip())
                st.rerun()

        st.divider()

        # --- Checkout ------------------------------------------------------
        if st.button(
            f"✅ Checkout — ₹{total:.0f}",
            type="primary",
            use_container_width=True,
        ):
            try:
                memory.update_memory(st.session_state.user_id, cart)
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Could not save order history: {exc}")
            st.balloons()
            st.success("Order placed! Estimated delivery: 12 minutes 🚀")
