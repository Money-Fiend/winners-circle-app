import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(
    page_title="Winner's circle",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color:#0d1117; }
[data-testid="stSidebar"]          { background-color:#161b22; }
.kpi-card {
    background:#161b22; border:1px solid #30363d;
    border-radius:10px; padding:18px 14px; text-align:center;
}
.kpi-card h2 { color:#58a6ff; font-size:1.9rem; margin:0; }
.kpi-card p  { color:#8b949e; margin:4px 0 0; font-size:.85rem; }
.player-header {
    background:linear-gradient(135deg,#161b22,#1f2937);
    border:1px solid #30363d; border-radius:12px;
    padding:20px 24px; margin-bottom:16px;
}
.player-header h2 { color:#f0f6fc; margin:0 0 4px; font-size:1.6rem; }
.player-header span { color:#8b949e; font-size:.9rem; }
.pos-badge {
    display:inline-block; padding:3px 10px; border-radius:6px;
    font-weight:bold; font-size:.8rem; margin-left:8px;
}
.pos-QB{background:#1d4ed8;color:#fff}
.pos-RB{background:#15803d;color:#fff}
.pos-WR{background:#b45309;color:#fff}
.pos-TE{background:#7e22ce;color:#fff}
.currency-pill {
    background:#1f2937; border:1px solid #3fb950;
    border-radius:20px; padding:6px 16px;
    color:#3fb950; font-weight:bold; font-size:1rem;
    display:inline-block;
}
</style>
""", unsafe_allow_html=True)

# ── Auth gate ─────────────────────────────────────────────────────────────────
from auth import show_login_page, refresh_currency
from db   import (query, query_one, write, fantasy_points, player_price,
                  process_currency, ADMIN_PASSWORD,
                  reset_player_stats, reset_team_records, reset_game_scores,
                  reset_all_games, reset_user_currency, reset_user_rosters, reset_bets,
                  ensure_bets_table, moneyline_odds, bet_payout,
                  place_bet, settle_pending_bets)

if not st.session_state.get("logged_in"):
    show_login_page()
    st.stop()

uid      = st.session_state["user_id"]
username = st.session_state["username"]

# One-time table init per session
if not st.session_state.get("_bets_init"):
    ensure_bets_table()
    st.session_state["_bets_init"] = True

# Process any unresolved game results → update currency & settle bets
process_currency(uid)
settle_pending_bets(uid)
currency = refresh_currency(uid)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## 🏈 NFL ")

    st.markdown(f"**{username}**")
    st.markdown(
        f'<div class="currency-pill">💰 ${currency:,.2f}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["Dashboard", "Standings", "Player Stats",
         "Marketplace", "My Lineup", "Fantasy Roster", "Moneyline", "Admin"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    if st.button("Logout", use_container_width=True):
        for k in ["logged_in","user_id","username","currency","auth_mode"]:
            st.session_state.pop(k, None)
        st.rerun()
    st.caption("nfl_2025 · MySQL")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    st.title("🏈 NFL 2025-26 Season Dashboard")

    _season_start = date(2026, 9, 9)
    _days_left = max(0, (_season_start - date.today()).days)
    if _days_left > 0:
        st.info(
            f"**2026 NFL Season kicks off September 9, 2026 — {_days_left} days away.** "
            "Use Admin → Season Reset to zero out stats before the new season."
        )
    else:
        st.success("**The 2026 NFL Season has begun!**")

    r1, _ = query("SELECT COUNT(*) FROM games WHERE home_score+away_score>0")
    r2, _ = query("SELECT COUNT(*) FROM players")
    r3, _ = query("SELECT COUNT(*) FROM stats")
    r4, _ = query("SELECT SUM(touchdowns) FROM stats")

    for col, val, lbl in zip(
        st.columns(4),
        [r1[0][0], r2[0][0], r3[0][0], int(r4[0][0] or 0)],
        ["Games Played","Players Tracked","Stat Entries","Total TDs"],
    ):
        col.markdown(f'<div class="kpi-card"><h2>{val}</h2><p>{lbl}</p></div>',
                     unsafe_allow_html=True)

    st.markdown("---")
    cl, cr = st.columns(2)

    with cl:
        st.subheader("Top Scorers — TDs")
        rows, cols = query("""
            SELECT CONCAT(p.first_name,' ',p.last_name) player,
                   p.position, t.team_name,
                   SUM(s.touchdowns) tds
            FROM stats s JOIN players p ON s.player_id=p.player_id
            JOIN team t ON p.team_id=t.team_id
            GROUP BY p.player_id, p.position, t.team_name
            ORDER BY tds DESC LIMIT 10
        """)
        if rows:
            st.dataframe(pd.DataFrame(rows, columns=cols),
                         use_container_width=True, hide_index=True)

    with cr:
        st.subheader("Top QBs — Passing Yards")
        rows, cols = query("""
            SELECT CONCAT(p.first_name,' ',p.last_name) player, t.team_name,
                   SUM(s.passing_yards) pass_yds,
                   SUM(s.touchdowns) tds, SUM(s.interceptions) ints
            FROM stats s JOIN players p ON s.player_id=p.player_id
            JOIN team t ON p.team_id=t.team_id
            WHERE p.position='QB'
            GROUP BY p.player_id, t.team_name ORDER BY pass_yds DESC
        """)
        if rows:
            st.dataframe(pd.DataFrame(rows, columns=cols),
                         use_container_width=True, hide_index=True)

    st.markdown("---")
    cl2, cr2 = st.columns(2)
    with cl2:
        st.subheader("Top Rushers")
        rows, cols = query("""
            SELECT CONCAT(p.first_name,' ',p.last_name) player,
                   p.position, t.team_name,
                   SUM(s.rushing_yards) rush_yds, SUM(s.touchdowns) tds
            FROM stats s JOIN players p ON s.player_id=p.player_id
            JOIN team t ON p.team_id=t.team_id
            WHERE p.position IN ('RB','QB')
            GROUP BY p.player_id, p.position, t.team_name
            ORDER BY rush_yds DESC LIMIT 8
        """)
        if rows:
            st.dataframe(pd.DataFrame(rows, columns=cols),
                         use_container_width=True, hide_index=True)

    with cr2:
        st.subheader("Top Receivers")
        rows, cols = query("""
            SELECT CONCAT(p.first_name,' ',p.last_name) player,
                   p.position, t.team_name,
                   SUM(s.receptions) rec, SUM(s.rushing_yards) rec_yds,
                   SUM(s.touchdowns) tds
            FROM stats s JOIN players p ON s.player_id=p.player_id
            JOIN team t ON p.team_id=t.team_id
            WHERE p.position IN ('WR','TE','RB')
            GROUP BY p.player_id, p.position, t.team_name
            ORDER BY rec DESC LIMIT 8
        """)
        if rows:
            st.dataframe(pd.DataFrame(rows, columns=cols),
                         use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# STANDINGS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Standings":
    st.title("📊 2025 NFL Standings")
    for conf in ["AFC","NFC"]:
        st.subheader(conf)
        rows, cols = query("""
            SELECT division, team_name, city, wins, losses,
                   ROUND(wins/(wins+losses)*100,1) win_pct
            FROM team WHERE conference=%s ORDER BY division, wins DESC
        """, (conf,))
        if rows:
            df = pd.DataFrame(rows, columns=cols)
            for div, grp in df.groupby("division", sort=False):
                st.markdown(f"**{conf} {div}**")
                st.dataframe(grp.drop(columns="division").reset_index(drop=True),
                             use_container_width=True, hide_index=True)
        st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# PLAYER STATS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Player Stats":
    st.title("🏃 Player Stats")

    p_rows, _ = query("""
        SELECT p.player_id,
               CONCAT(p.first_name,' ',p.last_name) name,
               p.position, t.team_name, p.age,
               MAX(r.jersey_number) jersey
        FROM players p JOIN team t ON p.team_id=t.team_id
        LEFT JOIN roster r ON p.player_id=r.player_id
        GROUP BY p.player_id, p.first_name, p.last_name, p.position, t.team_name, p.age
        ORDER BY p.position, p.last_name
    """)
    player_map = {f"{r[1]} ({r[2]} — {r[3]})": r for r in p_rows}
    sel = st.selectbox("Select a Player", list(player_map.keys()))
    pid, pname, pos, team, age, jersey = player_map[sel]

    badge = f"pos-{pos}"
    st.markdown(f"""
    <div class="player-header">
        <h2>#{jersey or '—'} &nbsp; {pname}
            <span class="pos-badge {badge}">{pos}</span>
        </h2>
        <span>{team} &nbsp;·&nbsp; Age {age}</span>
    </div>""", unsafe_allow_html=True)

    totals = query_one("""
        SELECT COUNT(*) games, SUM(passing_yards), SUM(rushing_yards),
               SUM(touchdowns), SUM(interceptions), SUM(receptions)
        FROM stats WHERE player_id=%s
    """, (pid,))
    games, pass_yds, rush_yds, tds, ints, rec = totals
    fpts = fantasy_points(pos, pass_yds, rush_yds, tds, ints, rec)

    st.markdown("#### Season Totals")
    if pos == "QB":
        for col, val, lbl in zip(
            st.columns(6),
            [games, int(pass_yds or 0), int(rush_yds or 0),
             int(tds or 0), int(ints or 0), fpts],
            ["Games","Pass Yds","Rush Yds","TDs","INTs","Fantasy Pts"],
        ):
            col.metric(lbl, val)
    elif pos == "RB":
        for col, val, lbl in zip(
            st.columns(5),
            [games, int(rush_yds or 0), int(tds or 0), int(rec or 0), fpts],
            ["Games","Rush Yds","TDs","Rec","Fantasy Pts"],
        ):
            col.metric(lbl, val)
    else:
        for col, val, lbl in zip(
            st.columns(5),
            [games, int(rush_yds or 0), int(rec or 0), int(tds or 0), fpts],
            ["Games","Rec Yds","Rec","TDs","Fantasy Pts"],
        ):
            col.metric(lbl, val)

    st.markdown("---")
    st.markdown("#### Game-by-Game Stats")

    game_rows, game_cols = query("""
        SELECT g.week, g.game_date,
               CASE WHEN g.home_team_id=p.team_id
                    THEN CONCAT('vs ',aw.team_name)
                    ELSE CONCAT('@ ', ht.team_name) END matchup,
               CASE WHEN g.home_team_id=p.team_id
                    THEN CONCAT(g.home_score,'-',g.away_score)
                    ELSE CONCAT(g.away_score,'-',g.home_score) END score,
               CASE WHEN (g.home_team_id=p.team_id AND g.home_score>g.away_score)
                      OR (g.away_team_id=p.team_id AND g.away_score>g.home_score)
                    THEN 'W' ELSE 'L' END result,
               s.passing_yards, s.rushing_yards,
               s.touchdowns, s.interceptions, s.receptions
        FROM stats s
        JOIN games   g  ON s.game_id=g.game_id
        JOIN players p  ON s.player_id=p.player_id
        JOIN team    ht ON g.home_team_id=ht.team_id
        JOIN team    aw ON g.away_team_id=aw.team_id
        WHERE s.player_id=%s
        ORDER BY g.game_date
    """, (pid,))

    if game_rows:
        df = pd.DataFrame(game_rows, columns=game_cols)
        ry_label = "Rush Yds" if pos in ("QB","RB") else "Rec Yds"
        df = df.rename(columns={
            "passing_yards":"Pass Yds", "rushing_yards": ry_label,
            "touchdowns":"TDs","interceptions":"INTs","receptions":"Rec",
        })
        df["Fant Pts"] = df.apply(lambda row: fantasy_points(
            pos, row.get("Pass Yds",0), row.get(ry_label,0),
            row["TDs"], row.get("INTs",0), row.get("Rec",0),
        ), axis=1)

        def color_result(val):
            return "color:#3fb950" if val=="W" else "color:#f85149"

        st.dataframe(df.style.map(color_result, subset=["result"]),
                     use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### Performance Charts")
        t1, t2 = st.tabs(["Fantasy Points per Game","Key Stats per Game"])
        with t1:
            st.line_chart(df.set_index("game_date")[["Fant Pts"]])
        with t2:
            if pos == "QB":
                st.line_chart(df.set_index("game_date")[["Pass Yds","Rush Yds","TDs"]])
            elif pos == "RB":
                st.line_chart(df.set_index("game_date")[["Rush Yds","TDs","Rec"]])
            else:
                st.line_chart(df.set_index("game_date")[["Rec Yds","Rec","TDs"]])
    else:
        st.info("No game stats found for this player.")


# ══════════════════════════════════════════════════════════════════════════════
# MARKETPLACE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Marketplace":
    st.title("🛒 Player Marketplace")
    st.markdown(
        f'**Your balance:** <span class="currency-pill">💰 ${currency:,.2f}</span>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Purchase players to add them to your lineup. "
        "Earn **+$50** each time a player's team wins a game, "
        "lose **-$25** when they lose."
    )
    st.markdown("---")

    # Already owned
    owned_rows, _ = query(
        "SELECT player_id FROM user_roster WHERE user_id=%s", (uid,)
    )
    owned_ids = {r[0] for r in owned_rows}

    all_rows, _ = query("""
        SELECT p.player_id,
               CONCAT(p.first_name,' ',p.last_name) name,
               p.position, t.team_name,
               MAX(r.jersey_number) jersey,
               COUNT(s.stat_id) games,
               SUM(s.passing_yards)  pass_yds,
               SUM(s.rushing_yards)  rush_yds,
               SUM(s.touchdowns)     tds,
               SUM(s.interceptions)  ints,
               SUM(s.receptions)     rec
        FROM players p JOIN team t ON p.team_id=t.team_id
        LEFT JOIN roster r ON p.player_id=r.player_id
        LEFT JOIN stats  s ON p.player_id=s.player_id
        GROUP BY p.player_id, p.first_name, p.last_name, p.position, t.team_name
        ORDER BY p.position, p.last_name
    """)

    pos_filter = st.multiselect(
        "Filter by position", ["QB","RB","WR","TE"],
        default=["QB","RB","WR","TE"]
    )

    for row in all_rows:
        pid_, name, pos_, team_, jersey_, games_, pyd, ryd, tds_, ints_, rec_ = row
        if pos_ not in pos_filter:
            continue

        fpts = fantasy_points(pos_, pyd, ryd, tds_, ints_, rec_)
        price = player_price(fpts)
        ppg   = round(fpts / max(1, games_), 1)
        is_owned = pid_ in owned_ids

        with st.container():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([3,1,1,1,1,1,2])
            c1.markdown(
                f"**#{jersey_ or '—'} {name}**  "
                f'<span class="pos-badge pos-{pos_}">{pos_}</span> '
                f"— {team_}",
                unsafe_allow_html=True,
            )
            c2.metric("Fant Pts", fpts)
            c3.metric("PPG",      ppg)
            c4.metric("Games",    games_)
            c5.metric("TDs",      int(tds_ or 0))
            c6.metric("Price",    f"${price}")

            if is_owned:
                c7.success("✅ Owned")
            elif currency < price:
                c7.warning(f"💸 Need ${price - currency:.0f} more")
            else:
                if c7.button(f"Buy for ${price}", key=f"buy_{pid_}", type="primary"):
                    ok = write("""
                        INSERT IGNORE INTO user_roster (user_id, player_id, purchase_price)
                        VALUES (%s, %s, %s)
                    """, (uid, pid_, price))
                    if ok:
                        write("""
                            UPDATE users SET currency = currency - %s WHERE user_id=%s
                        """, (price, uid))
                        st.success(f"Purchased {name}!")
                        refresh_currency(uid)
                        st.rerun()
            st.markdown('<hr style="border-color:#30363d;margin:6px 0">', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MY LINEUP
# ══════════════════════════════════════════════════════════════════════════════
elif page == "My Lineup":
    st.title("📋 My Lineup")
    st.markdown(
        f'**Current Balance:** <span class="currency-pill">💰 ${currency:,.2f}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    owned_rows, _ = query("""
        SELECT p.player_id,
               CONCAT(p.first_name,' ',p.last_name) name,
               p.position, t.team_name,
               MAX(r.jersey_number) jersey,
               ur.purchase_price, ur.purchased_at,
               COUNT(s.stat_id)      games,
               SUM(s.passing_yards)  pass_yds,
               SUM(s.rushing_yards)  rush_yds,
               SUM(s.touchdowns)     tds,
               SUM(s.interceptions)  ints,
               SUM(s.receptions)     rec
        FROM user_roster ur
        JOIN players p ON ur.player_id=p.player_id
        JOIN team    t ON p.team_id=t.team_id
        LEFT JOIN roster r ON p.player_id=r.player_id
        LEFT JOIN stats  s ON p.player_id=s.player_id
        WHERE ur.user_id=%s
        GROUP BY p.player_id, p.first_name, p.last_name,
                 p.position, t.team_name, ur.purchase_price, ur.purchased_at
        ORDER BY p.position, p.last_name
    """, (uid,))

    if not owned_rows:
        st.info("You don't own any players yet. Head to the **Marketplace** to buy some!")
    else:
        # Summary metrics
        total_fpts = sum(
            fantasy_points(r[2], r[8], r[9], r[10], r[11], r[12])
            for r in owned_rows
        )

        # Currency earned/lost from games
        log_rows, _ = query("""
            SELECT SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) earned,
                   SUM(CASE WHEN amount<0 THEN amount ELSE 0 END) lost,
                   COUNT(*) events
            FROM currency_log WHERE user_id=%s
        """, (uid,))
        earned = float(log_rows[0][0] or 0)
        lost   = float(log_rows[0][1] or 0)
        events = int(log_rows[0][2]   or 0)

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Players Owned", len(owned_rows))
        mc2.metric("Total Fant Pts", total_fpts)
        mc3.metric("💚 Earned",  f"${earned:,.0f}")
        mc4.metric("🔴 Lost",    f"${abs(lost):,.0f}")

        st.markdown("---")
        st.subheader("Roster")

        for row in owned_rows:
            (pid_, name, pos_, team_, jersey_,
             price_, bought_at_,
             games_, pyd, ryd, tds_, ints_, rec_) = row

            fpts  = fantasy_points(pos_, pyd, ryd, tds_, ints_, rec_)
            ppg   = round(fpts / max(1, games_), 1)
            badge = f"pos-{pos_}"

            with st.expander(
                f"#{jersey_ or '—'}  {name}  |  {pos_}  —  {team_}  |  "
                f"{fpts} pts  ({ppg} ppg)"
            ):
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Purchased for", f"${float(price_):.0f}")
                mc2.metric("Games Played",  games_)
                mc3.metric("TDs",           int(tds_ or 0))
                mc4.metric("Fantasy Pts",   fpts)

                # Game-by-game currency events for this player
                cl_rows, cl_cols = query("""
                    SELECT g.week, g.game_date,
                           CASE WHEN g.home_team_id=p.team_id
                                THEN CONCAT('vs ',aw.team_name)
                                ELSE CONCAT('@ ', ht.team_name) END matchup,
                           CASE WHEN g.home_team_id=p.team_id
                                THEN CONCAT(g.home_score,'-',g.away_score)
                                ELSE CONCAT(g.away_score,'-',g.home_score) END score,
                           cl.reason,
                           cl.amount
                    FROM currency_log cl
                    JOIN games   g  ON cl.game_id=g.game_id
                    JOIN players p  ON cl.player_id=p.player_id
                    JOIN team    ht ON g.home_team_id=ht.team_id
                    JOIN team    aw ON g.away_team_id=aw.team_id
                    WHERE cl.user_id=%s AND cl.player_id=%s
                    ORDER BY g.game_date
                """, (uid, pid_))

                if cl_rows:
                    cdf = pd.DataFrame(cl_rows, columns=cl_cols)

                    def color_amount(val):
                        if isinstance(val, (int, float)):
                            return "color:#3fb950" if val > 0 else "color:#f85149"
                        return ""

                    st.dataframe(
                        cdf.style.map(color_amount, subset=["amount"]),
                        use_container_width=True, hide_index=True,
                    )
                    net = sum(r[5] for r in cl_rows)
                    color = "#3fb950" if net >= 0 else "#f85149"
                    st.markdown(
                        f'Net from {name}: <span style="color:{color};font-weight:bold">'
                        f'{"+" if net>=0 else ""}${float(net):.2f}</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("No game results processed yet for this player.")

                st.markdown("---")
                if st.button(f"Release {name}", key=f"rel_{pid_}",
                             help="Remove from lineup (no refund)"):
                    write("DELETE FROM user_roster WHERE user_id=%s AND player_id=%s",
                          (uid, pid_))
                    st.warning(f"{name} released.")
                    st.rerun()

        st.markdown("---")
        st.subheader("Full Currency History")
        hist_rows, hist_cols = query("""
            SELECT g.week, g.game_date,
                   CONCAT(p.first_name,' ',p.last_name) player,
                   p.position,
                   cl.reason, cl.amount
            FROM currency_log cl
            JOIN players p ON cl.player_id=p.player_id
            JOIN games   g ON cl.game_id=g.game_id
            WHERE cl.user_id=%s
            ORDER BY g.game_date, p.last_name
        """, (uid,))
        if hist_rows:
            hdf = pd.DataFrame(hist_rows, columns=hist_cols)

            def color_amt(val):
                if isinstance(val, (int, float)):
                    return "color:#3fb950" if val > 0 else "color:#f85149"
                return ""

            st.dataframe(
                hdf.style.map(color_amt, subset=["amount"]),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No transactions yet.")


# ══════════════════════════════════════════════════════════════════════════════
# FANTASY ROSTER  (unchanged from before)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Fantasy Roster":
    st.title("🏆 Fantasy Football Roster")
    st.markdown("Build your lineup using PPR scoring "
                "(Pass TD=4, Rush/Rec TD=6, +1 per reception).")

    all_rows, _ = query("""
        SELECT p.player_id,
               CONCAT(p.first_name,' ',p.last_name) player,
               p.position, t.team_name,
               MAX(r.jersey_number)  jersey,
               COUNT(s.stat_id)      games,
               SUM(s.passing_yards)  pass_yds,
               SUM(s.rushing_yards)  rush_yds,
               SUM(s.touchdowns)     tds,
               SUM(s.interceptions)  ints,
               SUM(s.receptions)     rec
        FROM players p JOIN team t ON p.team_id=t.team_id
        LEFT JOIN roster r ON p.player_id=r.player_id
        LEFT JOIN stats  s ON p.player_id=s.player_id
        GROUP BY p.player_id, p.first_name, p.last_name, p.position, t.team_name
        ORDER BY p.position, p.last_name
    """)

    master = pd.DataFrame(all_rows, columns=[
        "player_id","player","position","team","jersey","games",
        "pass_yds","rush_yds","tds","ints","rec",
    ])
    master["fant_pts"] = master.apply(lambda r: fantasy_points(
        r["position"], r["pass_yds"], r["rush_yds"],
        r["tds"], r["ints"], r["rec"]
    ), axis=1)
    master["ppg"] = (master["fant_pts"] / master["games"].replace(0,1)).round(1)

    def player_options(pos_filter):
        subset = master[master["position"].isin(
            ["RB","WR","TE"] if pos_filter=="FLEX" else [pos_filter]
        )]
        return ["-- None --"] + [
            f"{r['player']} ({r['team']}) — {r['fant_pts']} pts"
            for _, r in subset.sort_values("fant_pts", ascending=False).iterrows()
        ]

    SLOTS = [("QB",1,"QB"),("RB",2,"RBs"),("WR",2,"WRs"),("TE",1,"TE"),("FLEX",1,"FLEX")]
    SLOT_KEYS = {"QB_0":"QB","RB_0":"RB1","RB_1":"RB2",
                 "WR_0":"WR1","WR_1":"WR2","TE_0":"TE","FLEX_0":"FLEX"}

    st.markdown("### 📋 Select Starters")
    picks = {}
    col1, col2 = st.columns(2)
    slot_cols = [col1, col1, col2, col2, col1]
    for (pos, cnt, lbl), sc in zip(SLOTS, slot_cols):
        with sc:
            st.markdown(f"**{lbl}**")
            for i in range(cnt):
                key = f"{pos}_{i}"
                picks[key] = st.selectbox(
                    f"{lbl} {i+1}" if cnt>1 else lbl,
                    player_options(pos), key=key,
                    label_visibility="collapsed",
                )

    with st.expander("+ Bench (up to 6)"):
        bench = [st.selectbox(f"Bench {i+1}",
                    ["-- None --"] + [
                        f"{r['player']} ({r['team']}) — {r['fant_pts']} pts"
                        for _, r in master.sort_values("fant_pts",ascending=False).iterrows()
                    ], key=f"bench_{i}")
                 for i in range(6)]

    def parse(s):
        if not s or s == "-- None --":
            return None
        name = s.split(" (")[0]
        row = master[master["player"]==name]
        return row.iloc[0] if not row.empty else None

    st.markdown("---")
    st.markdown("### 🏈 Your Roster")

    rows_out, total = [], 0.0
    for key, label in SLOT_KEYS.items():
        pr = parse(picks.get(key,""))
        if pr is not None:
            rows_out.append({"Slot":label,"Player":pr["player"],"Pos":pr["position"],
                             "Team":pr["team"],f"Jersey":f"#{int(pr['jersey']) if pr['jersey'] else '—'}",
                             "Games":int(pr["games"]),"Fant Pts":pr["fant_pts"],"PPG":pr["ppg"]})
            total += pr["fant_pts"]
        else:
            rows_out.append({"Slot":label,"Player":"—","Pos":"—","Team":"—",
                             "Jersey":"—","Games":0,"Fant Pts":0,"PPG":0})

    for i, pick in enumerate(bench):
        pr = parse(pick)
        if pr is not None:
            rows_out.append({"Slot":f"BN{i+1}","Player":pr["player"],"Pos":pr["position"],
                             "Team":pr["team"],"Jersey":f"#{int(pr['jersey']) if pr['jersey'] else '—'}",
                             "Games":int(pr["games"]),"Fant Pts":pr["fant_pts"],"PPG":pr["ppg"]})

    rdf = pd.DataFrame(rows_out)

    def s_slot(v): return "color:#8b949e;font-style:italic" if str(v).startswith("BN") else "color:#f0f6fc;font-weight:bold"
    def s_pts(v):  return "color:#3fb950" if isinstance(v,float) and v>0 else ""

    st.dataframe(rdf.style.map(s_slot,subset=["Slot"]).map(s_pts,subset=["Fant Pts","PPG"]),
                 use_container_width=True, hide_index=True)

    t1,t2,t3 = st.columns(3)
    filled = sum(1 for r in rows_out if r["Slot"] in SLOT_KEYS.values() and r["Player"]!="—")
    t1.metric("Starters Set", f"{filled}/{len(SLOT_KEYS)}")
    t2.metric("Total Fant Pts", round(total,1))
    t3.metric("Avg PPG", round(
        sum(r["PPG"] for r in rows_out if r["PPG"]>0)/max(1,sum(1 for r in rows_out if r["PPG"]>0)),1
    ))

    st.markdown("---")
    st.markdown("### 📦 Player Pool")
    pf = st.multiselect("Filter position",["QB","RB","WR","TE"],default=["QB","RB","WR","TE"])
    st.dataframe(
        master[master["position"].isin(pf)][
            ["player","position","team","jersey","games",
             "pass_yds","rush_yds","tds","ints","rec","fant_pts","ppg"]
        ].rename(columns={"player":"Player","position":"Pos","team":"Team",
                           "jersey":"Jersey #","games":"G","pass_yds":"Pass Yds",
                           "rush_yds":"Rush/Rec Yds","tds":"TDs","ints":"INTs",
                           "rec":"Rec","fant_pts":"Fant Pts","ppg":"PPG"})
        .sort_values("Fant Pts",ascending=False).reset_index(drop=True),
        use_container_width=True, hide_index=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# MONEYLINE BETTING
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Moneyline":
    st.title("📈 Moneyline Betting")
    st.markdown(
        f'**Balance:** <span class="currency-pill">💰 ${currency:,.2f}</span>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Odds are derived from each team's current win-loss record. "
        "Bets settle automatically when game scores are entered."
    )
    st.markdown("---")

    # Fetch this user's full bet history with team info
    my_bets, _ = query("""
        SELECT b.game_id, b.team_id, b.amount, b.odds,
               b.status, b.payout, b.placed_at,
               t.team_name, t.city
        FROM bets b
        JOIN team t ON b.team_id = t.team_id
        WHERE b.user_id = %s
        ORDER BY b.placed_at DESC
    """, (uid,))
    bet_game_ids = {r[0] for r in my_bets if r[4] == "pending"}

    tab_lines, tab_mybets = st.tabs(["🏟️ Open Lines", "🎫 My Bets"])

    # ── Open Lines ────────────────────────────────────────────────────────────
    with tab_lines:
        open_games, _ = query("""
            SELECT g.game_id, g.week, g.game_date,
                   ht.team_id,  ht.team_name,  ht.city,  ht.wins, ht.losses,
                   at2.team_id, at2.team_name, at2.city, at2.wins, at2.losses
            FROM games g
            JOIN team ht  ON g.home_team_id  = ht.team_id
            JOIN team at2 ON g.away_team_id  = at2.team_id
            WHERE g.home_score IS NULL OR g.away_score IS NULL
            ORDER BY g.game_date, g.week
        """)

        if not open_games:
            st.info(
                "No open betting lines right now. "
                "Lines appear for games that have been scheduled but not yet scored."
            )

        _card = (
            "background:#161b22;border:1px solid #30363d;"
            "border-radius:10px;padding:16px;text-align:center"
        )

        for (gid, week, gdate,
             h_tid, h_name, h_city, h_w, h_l,
             a_tid, a_name, a_city, a_w, a_l) in open_games:

            h_odds, a_odds = moneyline_odds(int(h_w), int(h_l), int(a_w), int(a_l))
            h_str = f"-{abs(h_odds)}" if h_odds < 0 else f"+{h_odds}"
            a_str = f"-{abs(a_odds)}" if a_odds < 0 else f"+{a_odds}"
            h_col = "#f85149" if h_odds < 0 else "#3fb950"
            a_col = "#f85149" if a_odds < 0 else "#3fb950"
            h_role = "FAVORITE" if h_odds < 0 else "UNDERDOG"
            a_role = "FAVORITE" if a_odds < 0 else "UNDERDOG"

            st.markdown(
                f"#### Week {week} &nbsp;·&nbsp; "
                f"{h_city} {h_name} vs {a_city} {a_name}"
            )
            st.caption(
                f"📅 {gdate}  |  "
                f"{h_city} {h_name} ({h_w}-{h_l}) hosts "
                f"{a_city} {a_name} ({a_w}-{a_l})"
            )

            # Odds cards
            oc1, oc2, oc3 = st.columns([5, 1, 5])
            with oc1:
                st.markdown(
                    f'<div style="{_card}">'
                    f'<div style="color:#f0f6fc;font-size:1rem;font-weight:bold;margin-bottom:6px">'
                    f'{h_city} {h_name}</div>'
                    f'<div style="color:{h_col};font-size:2.2rem;font-weight:bold">{h_str}</div>'
                    f'<div style="color:#8b949e;font-size:.75rem;margin-top:4px">'
                    f'{h_role} · ${bet_payout(100, h_odds):.0f} return per $100</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            oc2.markdown(
                '<div style="text-align:center;padding-top:26px;'
                'color:#8b949e;font-weight:bold;font-size:1rem">VS</div>',
                unsafe_allow_html=True,
            )
            with oc3:
                st.markdown(
                    f'<div style="{_card}">'
                    f'<div style="color:#f0f6fc;font-size:1rem;font-weight:bold;margin-bottom:6px">'
                    f'{a_city} {a_name}</div>'
                    f'<div style="color:{a_col};font-size:2.2rem;font-weight:bold">{a_str}</div>'
                    f'<div style="color:#8b949e;font-size:.75rem;margin-top:4px">'
                    f'{a_role} · ${bet_payout(100, a_odds):.0f} return per $100</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # Stats comparison
            with st.expander("📊 Head-to-Head Season Stats"):
                def _team_stats(tid):
                    gstat = query_one("""
                        SELECT COUNT(*),
                            COALESCE(SUM(CASE WHEN home_team_id=%s THEN home_score ELSE away_score END),0),
                            COALESCE(SUM(CASE WHEN home_team_id=%s THEN away_score ELSE home_score END),0)
                        FROM games
                        WHERE (home_team_id=%s OR away_team_id=%s)
                          AND home_score IS NOT NULL AND away_score IS NOT NULL
                    """, (tid, tid, tid, tid))
                    pstat = query_one("""
                        SELECT COALESCE(SUM(s.passing_yards),0),
                               COALESCE(SUM(s.rushing_yards),0),
                               COALESCE(SUM(s.touchdowns),0),
                               COALESCE(SUM(s.receptions),0)
                        FROM stats s
                        JOIN players p ON s.player_id = p.player_id
                        WHERE p.team_id = %s
                    """, (tid,))
                    return gstat or (0, 0, 0), pstat or (0, 0, 0, 0)

                hg, hs = _team_stats(h_tid)
                ag, as_ = _team_stats(a_tid)
                gp_h = int(hg[0]) or 1
                gp_a = int(ag[0]) or 1

                cmp_df = pd.DataFrame({
                    "Stat": [
                        "Record", "Points/G", "Points Allowed/G",
                        "Pass Yds/G", "Rush Yds/G", "Total TDs", "Total Rec",
                    ],
                    f"{h_city} {h_name}": [
                        f"{h_w}-{h_l}",
                        f"{float(hg[1])/gp_h:.1f}" if hg[0] else "—",
                        f"{float(hg[2])/gp_h:.1f}" if hg[0] else "—",
                        f"{float(hs[0])/gp_h:.1f}",
                        f"{float(hs[1])/gp_h:.1f}",
                        int(hs[2]),
                        int(hs[3]),
                    ],
                    f"{a_city} {a_name}": [
                        f"{a_w}-{a_l}",
                        f"{float(ag[1])/gp_a:.1f}" if ag[0] else "—",
                        f"{float(ag[2])/gp_a:.1f}" if ag[0] else "—",
                        f"{float(as_[0])/gp_a:.1f}",
                        f"{float(as_[1])/gp_a:.1f}",
                        int(as_[2]),
                        int(as_[3]),
                    ],
                })
                st.dataframe(cmp_df, use_container_width=True, hide_index=True)

            # Bet placement
            if gid in bet_game_ids:
                existing = next((r for r in my_bets if r[0] == gid), None)
                if existing:
                    e_odds_str = f"-{abs(existing[3])}" if existing[3] < 0 else f"+{existing[3]}"
                    pot = bet_payout(float(existing[2]), existing[3])
                    st.info(
                        f"🎫 Active bet: **${float(existing[2]):.0f}** on "
                        f"**{existing[8]} {existing[7]}** ({e_odds_str}) "
                        f"→ potential return **${pot:.2f}**"
                    )
            elif currency < 10:
                st.warning("Insufficient balance to place a bet (minimum $10).")
            else:
                with st.form(f"bet_{gid}"):
                    fb1, fb2, fb3 = st.columns([4, 2, 2])
                    bet_choice = fb1.radio(
                        "Pick a team",
                        [f"{h_city} {h_name} ({h_str})", f"{a_city} {a_name} ({a_str})"],
                        horizontal=True,
                        key=f"bc_{gid}",
                    )
                    bet_amt = fb2.number_input(
                        "Wager ($)",
                        min_value=10,
                        max_value=max(10, int(currency)),
                        step=10,
                        value=min(50, max(10, int(currency))),
                        key=f"ba_{gid}",
                    )
                    fb3.markdown("<br>", unsafe_allow_html=True)
                    bet_ok = fb3.form_submit_button(
                        "Place Bet 🎯", type="primary", use_container_width=True
                    )

                if bet_ok:
                    is_home = h_name in bet_choice
                    chosen_tid  = h_tid  if is_home else a_tid
                    chosen_odds = h_odds if is_home else a_odds
                    result = place_bet(uid, gid, chosen_tid, float(bet_amt), chosen_odds)
                    if result is True:
                        pot = bet_payout(float(bet_amt), chosen_odds)
                        st.success(
                            f"Bet placed! Wager: ${bet_amt:.0f} — "
                            f"return if win: ${pot:.2f}"
                        )
                        refresh_currency(uid)
                        st.rerun()
                    elif result == "insufficient":
                        st.error("Insufficient balance.")
                    elif result == "duplicate":
                        st.warning("You already have a bet on this game.")

            st.markdown(
                '<hr style="border-color:#21262d;margin:20px 0">',
                unsafe_allow_html=True,
            )

    # ── My Bets ───────────────────────────────────────────────────────────────
    with tab_mybets:
        if not my_bets:
            st.info("No bets placed yet. Head to **Open Lines** to get started.")
        else:
            pending_bets = [r for r in my_bets if r[4] == "pending"]
            settled_bets = [r for r in my_bets if r[4] != "pending"]
            won_bets     = [r for r in settled_bets if r[4] == "won"]

            total_staked   = sum(float(r[2]) for r in settled_bets)
            total_returned = sum(float(r[5]) for r in won_bets if r[5])
            net = total_returned - total_staked

            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Total Bets",   len(my_bets))
            sm2.metric("Pending",      len(pending_bets))
            sm3.metric("Win Rate",
                       f"{len(won_bets)/max(1,len(settled_bets)):.0%}")
            sm4.metric("Net P&L",      f"${net:+.2f}")

            if pending_bets:
                st.markdown("---")
                st.subheader("Active Bets")
                for r in pending_bets:
                    gid_, _, amt_, odds_, _, _, _, tname, tcity = r
                    o_str = f"-{abs(odds_)}" if odds_ < 0 else f"+{odds_}"
                    pot   = bet_payout(float(amt_), odds_)
                    g_info = query_one("""
                        SELECT g.week, g.game_date, ht.team_name, at2.team_name
                        FROM games g
                        JOIN team ht  ON g.home_team_id = ht.team_id
                        JOIN team at2 ON g.away_team_id = at2.team_id
                        WHERE g.game_id = %s
                    """, (gid_,))
                    matchup = (
                        f"Wk {g_info[0]} — {g_info[2]} vs {g_info[3]} ({g_info[1]})"
                        if g_info else f"Game {gid_}"
                    )
                    st.markdown(
                        f"🎫 **{matchup}** &nbsp;|&nbsp; "
                        f"Bet: **{tcity} {tname}** ({o_str}) &nbsp;|&nbsp; "
                        f"Wager: **${float(amt_):.0f}** &nbsp;|&nbsp; "
                        f"Potential: **${pot:.2f}**"
                    )

            if settled_bets:
                st.markdown("---")
                st.subheader("Bet History")
                hist = []
                for r in settled_bets:
                    gid_, _, amt_, odds_, status_, payout_, _, tname, tcity = r
                    o_str  = f"-{abs(odds_)}" if odds_ < 0 else f"+{odds_}"
                    g_info = query_one("""
                        SELECT g.week, g.game_date, ht.team_name, at2.team_name,
                               g.home_score, g.away_score
                        FROM games g
                        JOIN team ht  ON g.home_team_id = ht.team_id
                        JOIN team at2 ON g.away_team_id = at2.team_id
                        WHERE g.game_id = %s
                    """, (gid_,))
                    hist.append({
                        "Game":     (f"Wk{g_info[0]} {g_info[2]} vs {g_info[3]}"
                                     if g_info else f"Game {gid_}"),
                        "Date":     g_info[1] if g_info else "—",
                        "Bet On":   f"{tcity} {tname}",
                        "Odds":     o_str,
                        "Wagered":  float(amt_),
                        "Result":   status_.upper(),
                        "Returned": float(payout_) if payout_ else 0.0,
                        "Net":      (float(payout_) if payout_ else 0.0) - float(amt_),
                    })
                hdf = pd.DataFrame(hist)

                def _color_result(v):
                    if v == "WON":  return "color:#3fb950;font-weight:bold"
                    if v == "LOST": return "color:#f85149"
                    return "color:#8b949e"

                def _color_net(v):
                    if not isinstance(v, (int, float)): return ""
                    return "color:#3fb950" if v > 0 else "color:#f85149" if v < 0 else ""

                st.dataframe(
                    hdf.style
                       .map(_color_result, subset=["Result"])
                       .map(_color_net,    subset=["Net"]),
                    use_container_width=True,
                    hide_index=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Admin":
    st.title("🔧 Admin — Data Entry")

    if not st.session_state.get("admin_auth"):
        with st.form("admin_login"):
            pw = st.text_input("Admin password", type="password")
            if st.form_submit_button("Unlock", type="primary"):
                if pw == ADMIN_PASSWORD:
                    st.session_state["admin_auth"] = True
                    st.rerun()
                else:
                    st.error("Wrong password.")
        st.stop()

    st.success("Admin access granted.")
    if st.button("Lock Admin"):
        st.session_state.pop("admin_auth", None)
        st.rerun()
    st.markdown("---")

    tab_team, tab_player, tab_game, tab_roster, tab_stats, tab_reset = st.tabs(
        ["Teams", "Players", "Games", "Roster", "Stats", "Season Reset"]
    )

    # ── Teams ─────────────────────────────────────────────────────────────────
    with tab_team:
        st.subheader("Add / Update Team")
        with st.form("form_team"):
            col1, col2 = st.columns(2)
            team_name  = col1.text_input("Team Name", placeholder="Chiefs")
            city       = col2.text_input("City",      placeholder="Kansas City")
            conference = col1.selectbox("Conference", ["AFC", "NFC"])
            division   = col2.selectbox("Division",   ["North", "South", "East", "West"])
            wins       = col1.number_input("Wins",   min_value=0, max_value=17, step=1, value=0)
            losses     = col2.number_input("Losses", min_value=0, max_value=17, step=1, value=0)
            submitted  = st.form_submit_button("Insert Team", type="primary")

        if submitted:
            if not team_name or not city:
                st.error("Team name and city are required.")
            else:
                ok = write("""
                    INSERT INTO team (team_name, city, conference, division, wins, losses)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (team_name.strip(), city.strip(), conference, division, wins, losses))
                if ok:
                    st.success(f"Team '{team_name}' inserted (team_id={ok}).")

        st.markdown("---")
        st.subheader("Update Team")
        upd_team_opts, _ = query(
            "SELECT team_id, team_name, city, conference, division, wins, losses FROM team ORDER BY team_name"
        )
        upd_team_map = {r[1]: r for r in upd_team_opts}  # name → full row
        if upd_team_map:
            upd_label = st.selectbox("Select team to update", list(upd_team_map.keys()), key="upd_team_sel")
            ut = upd_team_map[upd_label]
            # ut: (team_id, team_name, city, conference, division, wins, losses)
            with st.form("form_update_team"):
                col1, col2 = st.columns(2)
                u_name  = col1.text_input("Team Name",  value=ut[1])
                u_city  = col2.text_input("City",       value=ut[2])
                u_conf  = col1.selectbox("Conference",  ["AFC", "NFC"],
                                         index=["AFC","NFC"].index(ut[3]))
                u_div   = col2.selectbox("Division",    ["North","South","East","West"],
                                         index=["North","South","East","West"].index(ut[4]))
                u_wins  = col1.number_input("Wins",   min_value=0, max_value=17, step=1, value=int(ut[5]))
                u_loss  = col2.number_input("Losses", min_value=0, max_value=17, step=1, value=int(ut[6]))
                upd_submit = st.form_submit_button("Save Changes", type="primary")
            if upd_submit:
                if not u_name or not u_city:
                    st.error("Team name and city are required.")
                else:
                    write("""
                        UPDATE team
                        SET team_name=%s, city=%s, conference=%s,
                            division=%s, wins=%s, losses=%s
                        WHERE team_id=%s
                    """, (u_name.strip(), u_city.strip(), u_conf, u_div,
                          u_wins, u_loss, ut[0]))
                    st.success(f"'{u_name}' updated.")
                    st.rerun()
        else:
            st.info("No teams to update.")

        st.markdown("---")
        st.subheader("Delete Team")
        del_team_opts, _ = query("SELECT team_id, CONCAT(city,' ',team_name) FROM team ORDER BY team_name")
        del_team_map = {r[1]: r[0] for r in del_team_opts}
        if del_team_map:
            with st.form("form_delete_team"):
                del_label   = st.selectbox("Select team to delete", list(del_team_map.keys()))
                confirmed   = st.checkbox("I understand this will also delete all related players, games, and stats")
                del_submit  = st.form_submit_button("Delete Team", type="primary")
            if del_submit:
                if not confirmed:
                    st.error("Check the confirmation box to proceed.")
                else:
                    tid = del_team_map[del_label]
                    write("DELETE FROM team WHERE team_id=%s", (tid,))
                    st.success(f"'{del_label}' deleted.")
                    st.rerun()
        else:
            st.info("No teams to delete.")

        st.markdown("---")
        st.subheader("Current Teams")
        t_rows, t_cols = query("SELECT team_id, team_name, city, conference, division, wins, losses FROM team ORDER BY conference, division, team_name")
        if t_rows:
            st.dataframe(pd.DataFrame(t_rows, columns=t_cols), use_container_width=True, hide_index=True)

    # ── Players ───────────────────────────────────────────────────────────────
    with tab_player:
        st.subheader("Add Player")
        team_opts, _ = query("SELECT team_id, CONCAT(city,' ',team_name) FROM team ORDER BY team_name")
        team_map = {f"{r[1]}": r[0] for r in team_opts}

        with st.form("form_player"):
            col1, col2 = st.columns(2)
            first_name = col1.text_input("First Name")
            last_name  = col2.text_input("Last Name")
            position   = col1.selectbox("Position", ["QB", "RB", "WR", "TE"])
            team_label = col2.selectbox("Team", list(team_map.keys()))
            age        = col1.number_input("Age", min_value=18, max_value=45, step=1, value=25)
            submitted  = st.form_submit_button("Insert Player", type="primary")

        if submitted:
            if not first_name or not last_name:
                st.error("First and last name are required.")
            elif not team_map:
                st.error("Add at least one team first.")
            else:
                ok = write("""
                    INSERT INTO players (first_name, last_name, position, team_id, age)
                    VALUES (%s, %s, %s, %s, %s)
                """, (first_name.strip(), last_name.strip(), position, team_map[team_label], age))
                if ok:
                    st.success(f"{first_name} {last_name} inserted (player_id={ok}).")

        st.markdown("---")
        st.subheader("Delete Player")
        del_player_opts, _ = query("""
            SELECT p.player_id,
                   CONCAT(p.first_name,' ',p.last_name,' (',p.position,' — ',t.city,' ',t.team_name,')')
            FROM players p JOIN team t ON p.team_id=t.team_id
            ORDER BY p.last_name
        """)
        del_player_map = {r[1]: r[0] for r in del_player_opts}
        if del_player_map:
            with st.form("form_delete_player"):
                del_p_label  = st.selectbox("Select player to delete", list(del_player_map.keys()))
                del_p_confirm = st.checkbox("I understand this will also delete all stats for this player")
                del_p_submit  = st.form_submit_button("Delete Player", type="primary")
            if del_p_submit:
                if not del_p_confirm:
                    st.error("Check the confirmation box to proceed.")
                else:
                    write("DELETE FROM players WHERE player_id=%s", (del_player_map[del_p_label],))
                    st.success(f"'{del_p_label}' deleted.")
                    st.rerun()
        else:
            st.info("No players to delete.")

        st.markdown("---")
        st.subheader("Current Players")
        p_rows, p_cols = query("""
            SELECT p.player_id, p.first_name, p.last_name, p.position,
                   CONCAT(t.city,' ',t.team_name) team, p.age
            FROM players p JOIN team t ON p.team_id=t.team_id
            ORDER BY p.last_name
        """)
        if p_rows:
            st.dataframe(pd.DataFrame(p_rows, columns=p_cols), use_container_width=True, hide_index=True)

    # ── Games ─────────────────────────────────────────────────────────────────
    with tab_game:
        st.subheader("Add Game")
        team_opts2, _ = query("SELECT team_id, CONCAT(city,' ',team_name) FROM team ORDER BY team_name")
        team_map2 = {f"{r[1]}": r[0] for r in team_opts2}
        team_labels = list(team_map2.keys())

        with st.form("form_game"):
            col1, col2 = st.columns(2)
            week        = col1.number_input("Week", min_value=1, max_value=22, step=1, value=1)
            game_date   = col2.date_input("Game Date")
            home_label  = col1.selectbox("Home Team", team_labels, key="home_team")
            away_label  = col2.selectbox("Away Team", team_labels, key="away_team")
            col3, col4  = st.columns(2)
            home_score  = col3.number_input("Home Score (blank = TBD)", min_value=-1, step=1, value=-1,
                                            help="Set to -1 to leave NULL (game not played yet)")
            away_score  = col4.number_input("Away Score (blank = TBD)", min_value=-1, step=1, value=-1)
            submitted   = st.form_submit_button("Insert Game", type="primary")

        if submitted:
            if not team_labels:
                st.error("Add teams first.")
            elif home_label == away_label:
                st.error("Home and away teams must be different.")
            else:
                hs = None if home_score < 0 else home_score
                as_ = None if away_score < 0 else away_score
                ok = write("""
                    INSERT INTO games (week, game_date, home_team_id, away_team_id, home_score, away_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (int(week), game_date.isoformat(),
                      team_map2[home_label], team_map2[away_label], hs, as_))
                if ok:
                    st.success(f"Game inserted (game_id={ok}).")

        st.markdown("---")
        st.subheader("Update Game")
        upd_game_opts, _ = query("""
            SELECT g.game_id, g.week, g.game_date,
                   g.home_team_id, g.away_team_id, g.home_score, g.away_score,
                   ht.team_name, at2.team_name
            FROM games g
            JOIN team ht  ON g.home_team_id=ht.team_id
            JOIN team at2 ON g.away_team_id=at2.team_id
            ORDER BY g.game_date DESC
        """)
        upd_game_map = {
            f"Wk{r[1]} {r[7]} vs {r[8]} ({r[2]})": r
            for r in upd_game_opts
        }
        upd_team_opts2, _ = query("SELECT team_id, CONCAT(city,' ',team_name) FROM team ORDER BY team_name")
        upd_team_map2 = {r[1]: r[0] for r in upd_team_opts2}
        team_labels2  = list(upd_team_map2.keys())

        if upd_game_map and team_labels2:
            upd_game_label = st.selectbox("Select game to update", list(upd_game_map.keys()), key="upd_game_sel")
            ug = upd_game_map[upd_game_label]
            # ug: (game_id, week, game_date, home_team_id, away_team_id, home_score, away_score, ht_name, at_name)
            cur_home_label = next((k for k, v in upd_team_map2.items() if v == ug[3]), team_labels2[0])
            cur_away_label = next((k for k, v in upd_team_map2.items() if v == ug[4]), team_labels2[0])
            with st.form("form_update_game"):
                col1, col2 = st.columns(2)
                ug_week  = col1.number_input("Week", min_value=1, max_value=22, step=1, value=int(ug[1]))
                ug_date  = col2.date_input("Game Date", value=ug[2])
                ug_home  = col1.selectbox("Home Team", team_labels2,
                                          index=team_labels2.index(cur_home_label), key="ug_home")
                ug_away  = col2.selectbox("Away Team", team_labels2,
                                          index=team_labels2.index(cur_away_label), key="ug_away")
                col3, col4 = st.columns(2)
                ug_hscore = col3.number_input("Home Score (-1 = NULL)", min_value=-1, step=1,
                                              value=int(ug[5]) if ug[5] is not None else -1)
                ug_ascore = col4.number_input("Away Score (-1 = NULL)", min_value=-1, step=1,
                                              value=int(ug[6]) if ug[6] is not None else -1)
                ug_submit = st.form_submit_button("Save Changes", type="primary")
            if ug_submit:
                if ug_home == ug_away:
                    st.error("Home and away teams must be different.")
                else:
                    hs2  = None if ug_hscore < 0 else ug_hscore
                    as2  = None if ug_ascore < 0 else ug_ascore
                    write("""
                        UPDATE games SET week=%s, game_date=%s,
                            home_team_id=%s, away_team_id=%s,
                            home_score=%s, away_score=%s
                        WHERE game_id=%s
                    """, (int(ug_week), ug_date.isoformat(),
                          upd_team_map2[ug_home], upd_team_map2[ug_away],
                          hs2, as2, ug[0]))
                    st.success("Game updated.")
                    st.rerun()
        else:
            st.info("No games to update.")

        st.markdown("---")
        st.subheader("Current Games")
        g_rows, g_cols = query("""
            SELECT g.game_id, g.week, g.game_date,
                   ht.team_name home_team, at2.team_name away_team,
                   g.home_score, g.away_score
            FROM games g
            JOIN team ht  ON g.home_team_id=ht.team_id
            JOIN team at2 ON g.away_team_id=at2.team_id
            ORDER BY g.game_date
        """)
        if g_rows:
            st.dataframe(pd.DataFrame(g_rows, columns=g_cols), use_container_width=True, hide_index=True)

    # ── Roster ────────────────────────────────────────────────────────────────
    with tab_roster:
        st.subheader("Assign Jersey Number")
        player_opts, _ = query("""
            SELECT p.player_id, CONCAT(p.first_name,' ',p.last_name,' (',p.position,')')
            FROM players p ORDER BY p.last_name
        """)
        player_map2 = {r[1]: r[0] for r in player_opts}

        with st.form("form_roster"):
            player_label  = st.selectbox("Player", list(player_map2.keys()))
            jersey_number = st.number_input("Jersey Number", min_value=1, max_value=99, step=1, value=1)
            submitted     = st.form_submit_button("Save Jersey", type="primary")

        if submitted:
            if not player_map2:
                st.error("Add players first.")
            else:
                ok = write("""
                    INSERT INTO roster (player_id, jersey_number)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE jersey_number=%s
                """, (player_map2[player_label], int(jersey_number), int(jersey_number)))
                if ok:
                    st.success(f"Jersey #{jersey_number} saved for {player_label}.")

        st.markdown("---")
        st.subheader("Update Jersey Number")
        upd_jersey_opts, _ = query("""
            SELECT p.player_id,
                   CONCAT(p.first_name,' ',p.last_name,' (',p.position,')') label,
                   r.jersey_number
            FROM roster r
            JOIN players p ON r.player_id=p.player_id
            ORDER BY p.last_name
        """)
        upd_jersey_map = {r[1]: (r[0], r[2]) for r in upd_jersey_opts}
        if upd_jersey_map:
            uj_label = st.selectbox("Select player", list(upd_jersey_map.keys()), key="upd_jersey_sel")
            uj_pid, uj_current = upd_jersey_map[uj_label]
            with st.form("form_update_jersey"):
                new_jersey = st.number_input("New Jersey Number", min_value=1, max_value=99,
                                             step=1, value=int(uj_current))
                uj_submit  = st.form_submit_button("Save Jersey", type="primary")
            if uj_submit:
                write("UPDATE roster SET jersey_number=%s WHERE player_id=%s",
                      (int(new_jersey), uj_pid))
                st.success(f"Jersey updated to #{new_jersey} for {uj_label}.")
                st.rerun()
        else:
            st.info("No roster entries to update.")

        st.markdown("---")
        st.subheader("Current Roster")
        r_rows, r_cols = query("""
            SELECT CONCAT(p.first_name,' ',p.last_name) player,
                   p.position, t.team_name, r.jersey_number
            FROM roster r
            JOIN players p ON r.player_id=p.player_id
            JOIN team    t ON p.team_id=t.team_id
            ORDER BY r.jersey_number
        """)
        if r_rows:
            st.dataframe(pd.DataFrame(r_rows, columns=r_cols), use_container_width=True, hide_index=True)

    # ── Stats ─────────────────────────────────────────────────────────────────
    with tab_stats:
        st.subheader("Add Game Stats")

        # Player picker outside the form so game list can react to the selection
        player_opts3, _ = query("""
            SELECT p.player_id,
                   CONCAT(p.first_name,' ',p.last_name,' (',p.position,')') label,
                   p.position, p.team_id,
                   CONCAT(t.city,' ',t.team_name) team_name
            FROM players p
            JOIN team t ON p.team_id=t.team_id
            ORDER BY p.last_name
        """)
        player_map3 = {r[1]: r for r in player_opts3}

        if not player_map3:
            st.info("Add players first.")
        else:
            ins_player_label = st.selectbox("Player", list(player_map3.keys()), key="ins_stat_player")
            ins_row          = player_map3[ins_player_label]
            ins_pid, ins_pos, ins_team_id, ins_team_name = ins_row[0], ins_row[2], ins_row[3], ins_row[4]

            st.caption(f"Showing games for the **{ins_team_name}**")

            # Only games where this player's team appears
            game_opts, _ = query("""
                SELECT g.game_id,
                       CONCAT('Wk',g.week,' ',ht.team_name,' vs ',at2.team_name,' (',g.game_date,')')
                FROM games g
                JOIN team ht  ON g.home_team_id=ht.team_id
                JOIN team at2 ON g.away_team_id=at2.team_id
                WHERE g.home_team_id=%s OR g.away_team_id=%s
                ORDER BY g.game_date DESC
            """, (ins_team_id, ins_team_id))
            game_map = {r[1]: r[0] for r in game_opts}

            if not game_map:
                st.warning(f"No games found for the {ins_team_name}. Add games first.")
            else:
                with st.form("form_stats"):
                    g_label  = st.selectbox("Game", list(game_map.keys()))
                    col3, col4 = st.columns(2)
                    pass_yds = col3.number_input("Passing Yards",  min_value=0, step=1, value=0)
                    rush_yds = col4.number_input("Rushing Yards",  min_value=0, step=1, value=0)
                    tds      = col3.number_input("Touchdowns",     min_value=0, step=1, value=0)
                    ints     = col4.number_input("Interceptions",  min_value=0, step=1, value=0)
                    rec      = col3.number_input("Receptions",     min_value=0, step=1, value=0)
                    submitted = st.form_submit_button("Insert Stats", type="primary")

                if submitted:
                    ok = write("""
                        INSERT INTO stats
                            (player_id, game_id, passing_yards, rushing_yards,
                             touchdowns, interceptions, receptions)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (ins_pid, game_map[g_label],
                          int(pass_yds), int(rush_yds), int(tds), int(ints), int(rec)))
                    if ok:
                        fpts = fantasy_points(ins_pos, pass_yds, rush_yds, tds, ints, rec)
                        st.success(f"Stats inserted (stat_id={ok}) — {fpts} fantasy pts.")

        st.markdown("---")
        st.subheader("Update Stats")

        # Step 1 — pick a player that has at least one stat entry
        upd_stat_players, _ = query("""
            SELECT DISTINCT p.player_id,
                   CONCAT(p.first_name,' ',p.last_name,' (',p.position,')') label,
                   p.position,
                   p.team_id
            FROM stats s
            JOIN players p ON s.player_id=p.player_id
            ORDER BY p.last_name
        """)
        upd_stat_player_map = {r[1]: (r[0], r[2], r[3]) for r in upd_stat_players}

        if not upd_stat_player_map:
            st.info("No stats to update.")
        else:
            us_player_label = st.selectbox(
                "Select player", list(upd_stat_player_map.keys()), key="upd_stat_player"
            )
            us_pid, us_pos, us_team_id = upd_stat_player_map[us_player_label]

            # Step 2 — only games where the player's team participated and a stat entry exists
            us_game_opts, _ = query("""
                SELECT s.stat_id,
                       CONCAT('Wk',g.week,' ',ht.team_name,' vs ',at2.team_name,
                              ' (',g.game_date,')') game_label,
                       s.passing_yards, s.rushing_yards,
                       s.touchdowns, s.interceptions, s.receptions
                FROM stats s
                JOIN games   g   ON s.game_id=g.game_id
                JOIN team    ht  ON g.home_team_id=ht.team_id
                JOIN team    at2 ON g.away_team_id=at2.team_id
                WHERE s.player_id=%s
                  AND (g.home_team_id=%s OR g.away_team_id=%s)
                ORDER BY g.game_date DESC
            """, (us_pid, us_team_id, us_team_id))
            us_game_map = {r[1]: r for r in us_game_opts}

            us_game_label = st.selectbox(
                "Select game", list(us_game_map.keys()), key="upd_stat_game"
            )
            us = us_game_map[us_game_label]
            # us: (stat_id, game_label, pass_yds, rush_yds, tds, ints, rec)

            with st.form("form_update_stats"):
                st.markdown(f"**{us_player_label}** — {us_game_label}")
                st.markdown("---")
                col1, col2 = st.columns(2)
                us_pass = col1.number_input("Passing Yards",  min_value=0, step=1, value=int(us[2] or 0))
                us_rush = col2.number_input("Rushing Yards",  min_value=0, step=1, value=int(us[3] or 0))
                us_tds  = col1.number_input("Touchdowns",     min_value=0, step=1, value=int(us[4] or 0))
                us_ints = col2.number_input("Interceptions",  min_value=0, step=1, value=int(us[5] or 0))
                us_rec  = col1.number_input("Receptions",     min_value=0, step=1, value=int(us[6] or 0))
                us_submit = st.form_submit_button("Save Changes", type="primary")

            if us_submit:
                write("""
                    UPDATE stats
                    SET passing_yards=%s, rushing_yards=%s,
                        touchdowns=%s, interceptions=%s, receptions=%s
                    WHERE stat_id=%s
                """, (int(us_pass), int(us_rush), int(us_tds),
                      int(us_ints), int(us_rec), us[0]))
                fpts = fantasy_points(us_pos, us_pass, us_rush, us_tds, us_ints, us_rec)
                st.success(f"Stats updated — {fpts} fantasy pts.")
                st.rerun()

        st.markdown("---")
        st.subheader("Recent Stats")
        st_rows, st_cols = query("""
            SELECT g.week, g.game_date,
                   CONCAT(p.first_name,' ',p.last_name) player, p.position,
                   s.passing_yards, s.rushing_yards,
                   s.touchdowns, s.interceptions, s.receptions
            FROM stats s
            JOIN players p ON s.player_id=p.player_id
            JOIN games   g ON s.game_id=g.game_id
            ORDER BY g.game_date DESC, p.last_name
            LIMIT 50
        """)
        if st_rows:
            st.dataframe(pd.DataFrame(st_rows, columns=st_cols), use_container_width=True, hide_index=True)

    # ── Season Reset ──────────────────────────────────────────────────────────
    with tab_reset:
        st.subheader("🔄 2026 Season Reset")

        _season_start = date(2026, 9, 9)
        _days_left = max(0, (_season_start - date.today()).days)
        rc1, rc2 = st.columns(2)
        rc1.metric("2026 Season Kickoff", "September 9, 2026")
        rc2.metric("Days Until Kickoff", _days_left)

        st.markdown("---")
        st.error(
            "⚠️ **Danger Zone** — these actions are permanent and cannot be undone. "
            "Run this before the 2026 season begins to start fresh."
        )
        st.markdown("**Select what to reset:**")

        do_stats    = st.checkbox("Clear all player game stats (sets every stat to 0)", value=True)
        do_records  = st.checkbox("Reset all team win/loss records to 0-0", value=True)
        do_scores   = st.checkbox("Reset game scores to TBD (keeps schedule)", value=False)
        do_games    = st.checkbox("Delete entire game schedule", value=False)
        do_currency = st.checkbox("Reset all user currency to $1,000 and clear earnings history", value=False)
        do_rosters  = st.checkbox("Clear all user fantasy rosters", value=False)
        do_bets     = st.checkbox("Clear all moneyline bets and history", value=False)

        if do_games and do_scores:
            st.warning("Both 'Delete schedule' and 'Reset scores' are checked — only the full delete will run.")

        st.markdown("---")
        confirmed_reset = st.checkbox(
            "I understand this is permanent and cannot be undone — proceed with reset"
        )

        if st.button("Execute Season Reset", type="primary", disabled=not confirmed_reset):
            results = []
            if do_stats:
                reset_player_stats()
                results.append("Player stats cleared")
            if do_records:
                reset_team_records()
                results.append("Team records reset to 0-0")
            if do_games:
                reset_all_games()
                results.append("Game schedule deleted")
            elif do_scores:
                reset_game_scores()
                results.append("Game scores reset to TBD")
            if do_currency:
                reset_user_currency()
                results.append("User currency reset to $1,000 and earnings history cleared")
            if do_rosters:
                reset_user_rosters()
                results.append("User fantasy rosters cleared")
            if do_bets:
                reset_bets()
                results.append("Moneyline bets cleared")

            if results:
                st.success("Season reset complete:\n" + "\n".join(f"- {r}" for r in results))
            else:
                st.info("Nothing selected to reset.")
