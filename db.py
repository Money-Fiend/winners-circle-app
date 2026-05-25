import pymysql
import pymysql.cursors
from pymysql import Error
import streamlit as st

DB_CONFIG = {
    "host":     st.secrets["mysql"]["host"],
    "user":     st.secrets["mysql"]["user"],
    "password": st.secrets["mysql"]["password"],
    "database": st.secrets["mysql"]["database"],
    "port":     int(st.secrets["mysql"]["port"]),
}

ADMIN_PASSWORD = "nfl_admin_2025"

WIN_BONUS  =  50.00   # $ earned per player when their team wins
LOSS_PENALTY = 25.00  # $ lost  per player when their team loses


@st.cache_resource
def get_connection():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        return conn
    except Error as e:
        st.error(f"Could not connect to MySQL: {e}")
        return None


def _cursor():
    conn = get_connection()
    if conn:
        try:
            conn.ping(reconnect=True)
        except Exception:
            pass
    return conn


def query(sql: str, params: tuple = ()):
    conn = _cursor()
    if conn is None:
        return [], []
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
        return rows, cols
    except Error as e:
        st.error(f"Query error: {e}")
        return [], []


def query_one(sql: str, params: tuple = ()):
    rows, _ = query(sql, params)
    return rows[0] if rows else None


def write(sql: str, params: tuple = ()):
    conn = _cursor()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        last = cur.lastrowid
        cur.close()
        return last or True
    except Error as e:
        conn.rollback()
        st.error(f"Write error: {e}")
        return None


# ── Player pricing ────────────────────────────────────────────────────────────
def player_price(fant_pts: float) -> int:
    """Round fantasy-point total to nearest $10, floor $50."""
    return max(50, round(float(fant_pts) / 10) * 10)


# ── Fantasy scoring (PPR) ─────────────────────────────────────────────────────
def fantasy_points(pos, pass_yds, rush_yds, tds, ints, rec) -> float:
    p  = float(pass_yds or 0)
    r  = float(rush_yds or 0)
    t  = float(tds      or 0)
    i  = float(ints     or 0)
    rc = float(rec      or 0)
    if pos == "QB":
        return round(p * 0.04 + r * 0.1 + t * 4 - i * 2, 1)
    return round(r * 0.1 + t * 6 + rc, 1)


# ── Currency: process game results for owned players ─────────────────────────
# ── Season reset helpers ──────────────────────────────────────────────────────
def reset_player_stats():
    return write("DELETE FROM stats")

def reset_team_records():
    return write("UPDATE team SET wins=0, losses=0")

def reset_game_scores():
    return write("UPDATE games SET home_score=NULL, away_score=NULL")

def reset_all_games():
    return write("DELETE FROM games")

def reset_user_currency():
    write("DELETE FROM currency_log")
    return write("UPDATE users SET currency=1000.00")

def reset_user_rosters():
    return write("DELETE FROM user_roster")

def reset_bets():
    return write("DELETE FROM bets")


# ── Moneyline betting ─────────────────────────────────────────────────────────
def ensure_bets_table():
    write("""
        CREATE TABLE IF NOT EXISTS bets (
            bet_id    INT AUTO_INCREMENT PRIMARY KEY,
            user_id   INT NOT NULL,
            game_id   INT NOT NULL,
            team_id   INT NOT NULL,
            amount    DECIMAL(10,2) NOT NULL,
            odds      INT NOT NULL,
            status    ENUM('pending','won','lost','push') DEFAULT 'pending',
            payout    DECIMAL(10,2) DEFAULT NULL,
            placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (game_id) REFERENCES games(game_id),
            FOREIGN KEY (team_id) REFERENCES team(team_id)
        )
    """)


def moneyline_odds(home_w, home_l, away_w, away_l):
    """Return (home_odds, away_odds) as American integers, rounded to nearest 5."""
    hw = home_w / (home_w + home_l) if (home_w + home_l) > 0 else 0.5
    aw = away_w / (away_w + away_l) if (away_w + away_l) > 0 else 0.5
    total = (hw + aw) or 1.0
    hp, ap = hw / total, aw / total
    hp = min(0.95, max(0.05, hp * 1.0476))
    ap = min(0.95, max(0.05, ap * 1.0476))

    def to_ml(p):
        if p >= 0.5:
            raw = p / (1 - p) * 100
            return -max(100, int(round(raw / 5) * 5))
        raw = (1 - p) / p * 100
        return max(100, int(round(raw / 5) * 5))

    return to_ml(hp), to_ml(ap)


def bet_payout(amount: float, odds: int) -> float:
    """Total return (stake + profit) for a winning bet."""
    if odds > 0:
        return round(float(amount) * (1 + odds / 100), 2)
    return round(float(amount) * (1 + 100 / abs(odds)), 2)


def place_bet(user_id, game_id, team_id, amount, odds):
    conn = _cursor()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT currency FROM users WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        if not row or float(row[0]) < amount:
            cur.close()
            return "insufficient"
        cur.execute(
            "SELECT bet_id FROM bets WHERE user_id=%s AND game_id=%s",
            (user_id, game_id),
        )
        if cur.fetchone():
            cur.close()
            return "duplicate"
        cur.execute(
            "INSERT INTO bets (user_id, game_id, team_id, amount, odds) VALUES (%s,%s,%s,%s,%s)",
            (user_id, game_id, team_id, amount, odds),
        )
        cur.execute(
            "UPDATE users SET currency = GREATEST(0, currency - %s) WHERE user_id=%s",
            (amount, user_id),
        )
        conn.commit()
        cur.close()
        return True
    except Error as e:
        conn.rollback()
        st.error(f"Bet error: {e}")
        return None


def settle_pending_bets(user_id):
    """Settle bets on completed games and credit winnings to user."""
    conn = _cursor()
    if conn is None:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT b.bet_id, b.team_id, b.amount, b.odds,
                   g.home_team_id, g.away_team_id, g.home_score, g.away_score
            FROM bets b
            JOIN games g ON b.game_id = g.game_id
            WHERE b.user_id = %s
              AND b.status  = 'pending'
              AND g.home_score IS NOT NULL
              AND g.away_score IS NOT NULL
        """, (user_id,))
        for bet_id, team_id, amount, odds, h_tid, a_tid, h_sc, a_sc in cur.fetchall():
            if h_sc == a_sc:
                status, payout = "push", float(amount)
            elif (team_id == h_tid and h_sc > a_sc) or (team_id == a_tid and a_sc > h_sc):
                status, payout = "won", bet_payout(float(amount), odds)
            else:
                status, payout = "lost", 0.0
            cur.execute(
                "UPDATE bets SET status=%s, payout=%s WHERE bet_id=%s",
                (status, payout, bet_id),
            )
            if payout > 0:
                cur.execute(
                    "UPDATE users SET currency = currency + %s WHERE user_id=%s",
                    (payout, user_id),
                )
        conn.commit()
        cur.close()
    except Error as e:
        st.error(f"Bet settlement error: {e}")


def process_currency(user_id: int):
    """
    For every game a user's owned players participated in, apply win/loss
    adjustments that haven't been logged yet. Updates users.currency in DB.
    """
    conn = _cursor()
    if conn is None:
        return

    try:
        cur = conn.cursor()

        # Owned player_ids for this user
        cur.execute("SELECT player_id FROM user_roster WHERE user_id=%s", (user_id,))
        owned = [r[0] for r in cur.fetchall()]
        if not owned:
            cur.close()
            return

        fmt = ",".join(["%s"] * len(owned))

        # Games those players participated in, excluding already-logged ones
        cur.execute(f"""
            SELECT s.player_id, s.game_id,
                   p.team_id,
                   g.home_team_id, g.away_team_id,
                   g.home_score,   g.away_score
            FROM stats s
            JOIN players p ON s.player_id = p.player_id
            JOIN games   g ON s.game_id   = g.game_id
            WHERE s.player_id IN ({fmt})
              AND g.home_score IS NOT NULL
              AND g.away_score IS NOT NULL
              AND g.home_score + g.away_score > 0
              AND NOT EXISTS (
                  SELECT 1 FROM currency_log cl
                  WHERE cl.user_id   = %s
                    AND cl.player_id = s.player_id
                    AND cl.game_id   = s.game_id
              )
        """, (*owned, user_id))

        events = cur.fetchall()
        delta  = 0.0

        for player_id, game_id, team_id, home_id, away_id, home_sc, away_sc in events:
            home_win = home_sc > away_sc
            player_home = (team_id == home_id)
            won = (player_home and home_win) or (not player_home and not home_win)

            amount = WIN_BONUS if won else -LOSS_PENALTY
            delta += amount
            reason = "Win bonus" if won else "Loss penalty"

            cur.execute("""
                INSERT IGNORE INTO currency_log
                    (user_id, player_id, game_id, amount, reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, player_id, game_id, amount, reason))

        if delta != 0:
            cur.execute(
                "UPDATE users SET currency = GREATEST(0, currency + %s) WHERE user_id=%s",
                (delta, user_id),
            )

        conn.commit()
        cur.close()
    except Error as e:
        st.error(f"Currency processing error: {e}")
