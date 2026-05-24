import hashlib, os
import streamlit as st
from db import query, query_one, get_connection
from mysql.connector import Error


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


def login(username: str, password: str):
    """Return user row dict on success, None on failure."""
    row = query_one(
        "SELECT user_id, username, password_hash, currency FROM users WHERE username=%s",
        (username,),
    )
    if row and verify_password(row[2], password):
        return {"user_id": row[0], "username": row[1], "currency": float(row[3])}
    return None


def register(username: str, password: str):
    """Create account. Returns error string or None on success."""
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    conn = get_connection()
    if conn is None:
        return "Database unavailable."
    try:
        if not conn.is_connected():
            conn.reconnect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, currency) VALUES (%s, %s, 1000.00)",
            (username, hash_password(password)),
        )
        conn.commit()
        cur.close()
        return None
    except Error as e:
        if e.errno == 1062:
            return "Username already taken."
        return f"Registration failed: {e}"


def refresh_currency(user_id: int) -> float:
    """Re-read current currency from DB and update session state."""
    row = query_one("SELECT currency FROM users WHERE user_id=%s", (user_id,))
    val = float(row[0]) if row else 0.0
    st.session_state["currency"] = val
    return val


def show_login_page():
    """Render login / register form. Sets session state on success."""
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background:#0d1117; }
    .login-box {
        max-width: 400px; margin: 60px auto;
        background:#161b22; border:1px solid #30363d;
        border-radius:14px; padding:36px 32px;
    }
    .login-box h2 { color:#f0f6fc; text-align:center; margin-bottom:24px; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-box"><h2>🏈 NFL Fantasy Dashboard</h2></div>',
                unsafe_allow_html=True)

    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "login"

    col1, col2 = st.columns(2)
    if col1.button("Login",    use_container_width=True,
                   type="primary" if st.session_state["auth_mode"] == "login" else "secondary"):
        st.session_state["auth_mode"] = "login"
    if col2.button("Register", use_container_width=True,
                   type="primary" if st.session_state["auth_mode"] == "register" else "secondary"):
        st.session_state["auth_mode"] = "register"

    st.markdown("---")

    if st.session_state["auth_mode"] == "login":
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True, type="primary")
        if submitted:
            user = login(username.strip(), password)
            if user:
                st.session_state["user_id"]  = user["user_id"]
                st.session_state["username"] = user["username"]
                st.session_state["currency"] = user["currency"]
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("Invalid username or password.")

    else:
        with st.form("register_form"):
            new_user = st.text_input("Choose a username")
            new_pass = st.text_input("Choose a password", type="password")
            confirm  = st.text_input("Confirm password",  type="password")
            submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
        if submitted:
            if new_pass != confirm:
                st.error("Passwords do not match.")
            else:
                err = register(new_user.strip(), new_pass)
                if err:
                    st.error(err)
                else:
                    st.success("Account created! Please log in.")
                    st.session_state["auth_mode"] = "login"
                    st.rerun()
