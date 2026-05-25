import hashlib, os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import streamlit as st
from db import (query, query_one, get_connection,
                email_exists, store_reset_code,
                verify_reset_code, update_password_by_email)
from pymysql import Error


# ── Password hashing ──────────────────────────────────────────────────────────
def _hash(password: str, salt: bytes) -> str:
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return key.hex()


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    return salt.hex() + ":" + _hash(password, salt)


def verify_password(stored: str, provided: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        return _hash(provided, bytes.fromhex(salt_hex)) == key_hex
    except Exception:
        return False


# ── Email sending ─────────────────────────────────────────────────────────────
def send_reset_email(to_email: str, code: str) -> bool:
    """Send a password-reset code via Gmail SMTP. Returns True on success."""
    try:
        smtp_user = st.secrets["email"]["smtp_user"]
        smtp_pass = st.secrets["email"]["smtp_password"]
    except Exception:
        return False   # email secrets not configured

    subject = "🏈 Winner's Circle — Password Reset Code"
    plain = (
        f"Your password reset code is: {code}\n\n"
        "This code expires in 15 minutes.\n"
        "If you didn't request a reset, ignore this email."
    )
    html = f"""
    <div style="font-family:sans-serif;max-width:420px;margin:auto;
                padding:28px;background:#161b22;border-radius:14px;color:#f0f6fc">
      <h2 style="color:#58a6ff;margin-top:0">🏈 Winner's Circle</h2>
      <p style="color:#8b949e">Your password reset code:</p>
      <div style="font-size:2.4rem;font-weight:bold;letter-spacing:10px;
                  color:#3fb950;text-align:center;padding:18px;
                  background:#0d1117;border-radius:10px;margin:16px 0">
        {code}
      </div>
      <p style="color:#8b949e;font-size:.85rem">
        Expires in <strong>15 minutes</strong>.<br>
        If you didn't request this, ignore the email.
      </p>
    </div>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as srv:
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, to_email, msg.as_string())
        return True
    except Exception:
        return False


# ── Auth helpers ──────────────────────────────────────────────────────────────
def login(username: str, password: str):
    """Return user dict on success, None on failure."""
    row = query_one(
        "SELECT user_id, username, password_hash, currency FROM users WHERE username=%s",
        (username,),
    )
    if row and verify_password(row[2], password):
        return {"user_id": row[0], "username": row[1], "currency": float(row[3])}
    return None


def register(username: str, email: str, password: str):
    """Create account. Returns error string or None on success."""
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if "@" not in email or "." not in email:
        return "Please enter a valid email address."
    if len(password) < 6:
        return "Password must be at least 6 characters."

    conn = get_connection()
    if conn is None:
        return "Database unavailable."
    try:
        conn.ping(reconnect=True)
        cur = conn.cursor()
        # Check duplicate email
        cur.execute("SELECT user_id FROM users WHERE email=%s", (email.lower().strip(),))
        if cur.fetchone():
            cur.close()
            return "An account with that email already exists."
        cur.execute(
            "INSERT INTO users (username, email, password_hash, currency) "
            "VALUES (%s, %s, %s, 1000.00)",
            (username, email.lower().strip(), hash_password(password)),
        )
        conn.commit()
        cur.close()
        return None
    except Error as e:
        if getattr(e, "args", None) and e.args[0] == 1062:
            return "Username already taken."
        return f"Registration failed: {e}"


def refresh_currency(user_id: int) -> float:
    """Re-read current currency from DB and update session state."""
    row = query_one("SELECT currency FROM users WHERE user_id=%s", (user_id,))
    val = float(row[0]) if row else 0.0
    st.session_state["currency"] = val
    return val


# ── Login page ────────────────────────────────────────────────────────────────
def show_login_page():
    """Render login / register / forgot-password flow."""
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background:#0d1117; }
    .login-box {
        max-width:420px; margin:60px auto;
        background:#161b22; border:1px solid #30363d;
        border-radius:14px; padding:36px 32px;
    }
    .login-box h2 { color:#f0f6fc; text-align:center; margin-bottom:24px; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div class="login-box"><h2>🏈 NFL Fantasy Dashboard</h2></div>',
        unsafe_allow_html=True,
    )

    # ── initialise mode ────────────────────────────────────────────────────────
    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "login"

    mode = st.session_state["auth_mode"]

    # ── top nav (only on login / register) ────────────────────────────────────
    if mode in ("login", "register"):
        c1, c2 = st.columns(2)
        if c1.button("Login", use_container_width=True,
                     type="primary" if mode == "login" else "secondary"):
            st.session_state["auth_mode"] = "login"
            st.rerun()
        if c2.button("Register", use_container_width=True,
                     type="primary" if mode == "register" else "secondary"):
            st.session_state["auth_mode"] = "register"
            st.rerun()
        st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # LOGIN
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "login":
        with st.form("login_form"):
            username  = st.text_input("Username")
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Login", use_container_width=True, type="primary"
            )
        if submitted:
            user = login(username.strip(), password)
            if user:
                st.session_state.update({
                    "user_id":   user["user_id"],
                    "username":  user["username"],
                    "currency":  user["currency"],
                    "logged_in": True,
                })
                st.rerun()
            else:
                st.error("Invalid username or password.")

        # Forgot password link
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔑 Forgot your password?", use_container_width=True,
                     type="secondary"):
            st.session_state["auth_mode"] = "forgot_email"
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTER
    # ══════════════════════════════════════════════════════════════════════════
    elif mode == "register":
        with st.form("register_form"):
            new_user  = st.text_input("Choose a username")
            new_email = st.text_input("Email address")
            new_pass  = st.text_input("Choose a password",  type="password")
            confirm   = st.text_input("Confirm password",   type="password")
            submitted = st.form_submit_button(
                "Create Account", use_container_width=True, type="primary"
            )
        if submitted:
            if new_pass != confirm:
                st.error("Passwords do not match.")
            else:
                err = register(new_user.strip(), new_email.strip(), new_pass)
                if err:
                    st.error(err)
                else:
                    st.success("Account created! Please log in.")
                    st.session_state["auth_mode"] = "login"
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # FORGOT PASSWORD — Step 1: enter email
    # ══════════════════════════════════════════════════════════════════════════
    elif mode == "forgot_email":
        st.markdown("### 🔑 Reset Password")
        st.caption("Enter the email address linked to your account.")

        with st.form("forgot_email_form"):
            reset_email = st.text_input("Email address")
            submitted   = st.form_submit_button(
                "Send Reset Code", use_container_width=True, type="primary"
            )

        if submitted:
            reset_email = reset_email.strip().lower()
            if not reset_email or "@" not in reset_email:
                st.error("Please enter a valid email address.")
            elif not email_exists(reset_email):
                # Don't reveal whether email exists — generic message
                st.info(
                    "If that email is registered, a reset code has been sent. "
                    "Check your inbox (and spam folder)."
                )
                # Still proceed so timing doesn't leak user existence
                st.session_state["reset_email"] = reset_email
                st.session_state["auth_mode"]   = "forgot_code"
                st.rerun()
            else:
                code    = store_reset_code(reset_email)
                emailed = send_reset_email(reset_email, code)
                st.session_state["reset_email"] = reset_email

                if emailed:
                    st.success("Reset code sent! Check your inbox.")
                else:
                    # Email service not set up — show code on screen for dev/admin
                    st.warning(
                        f"Email service not configured. Your reset code is: **{code}**  \n"
                        "*(Set up `[email]` in Streamlit secrets to send real emails.)*"
                    )

                st.session_state["auth_mode"] = "forgot_code"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Back to Login", use_container_width=True, type="secondary"):
            st.session_state["auth_mode"] = "login"
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # FORGOT PASSWORD — Step 2: enter code + new password
    # ══════════════════════════════════════════════════════════════════════════
    elif mode == "forgot_code":
        st.markdown("### 🔑 Reset Password")
        email_hint = st.session_state.get("reset_email", "your email")
        st.caption(f"Enter the 6-digit code sent to **{email_hint}** and choose a new password.")

        with st.form("forgot_code_form"):
            code      = st.text_input("6-digit code", max_chars=6,
                                      placeholder="123456")
            new_pass  = st.text_input("New password",     type="password")
            confirm   = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button(
                "Reset Password", use_container_width=True, type="primary"
            )

        if submitted:
            reset_email = st.session_state.get("reset_email", "")
            if not code.strip():
                st.error("Please enter the reset code.")
            elif new_pass != confirm:
                st.error("Passwords do not match.")
            elif len(new_pass) < 6:
                st.error("Password must be at least 6 characters.")
            elif not verify_reset_code(reset_email, code.strip()):
                st.error("Invalid or expired code. Please request a new one.")
            else:
                ok = update_password_by_email(reset_email, hash_password(new_pass))
                if ok:
                    st.success("✅ Password updated! You can now log in.")
                    # Clean up reset session state
                    st.session_state.pop("reset_email", None)
                    st.session_state["auth_mode"] = "login"
                    st.rerun()
                else:
                    st.error("Could not update password. Please try again.")

        st.markdown("<br>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        if col_a.button("← Back to Login", use_container_width=True, type="secondary"):
            st.session_state["auth_mode"] = "login"
            st.rerun()
        if col_b.button("Resend Code", use_container_width=True, type="secondary"):
            reset_email = st.session_state.get("reset_email", "")
            if reset_email and email_exists(reset_email):
                code    = store_reset_code(reset_email)
                emailed = send_reset_email(reset_email, code)
                if emailed:
                    st.success("New code sent!")
                else:
                    st.warning(f"Email not configured. New code: **{code}**")
            st.rerun()
