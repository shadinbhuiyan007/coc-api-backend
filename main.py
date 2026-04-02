import os
import asyncio
import logging
import threading
import time
from datetime import datetime

import coc
from flask import Flask, jsonify
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins="*")

COC_EMAIL = "mehadishadin007@gmail.com"
COC_PASSWORD = "23241893$$Ss"
CLAN_TAG = "GVUPYPLC"


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)


def normalize_tag(tag):
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag.upper()


def error_response(message, status=500):
    return jsonify({"error": message}), status


@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "CoC API is running"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "clan_tag": CLAN_TAG,
        "credentials_configured": bool(COC_EMAIL and COC_PASSWORD)
    })


@app.route("/clan", methods=["GET"])
def get_clan():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("COC_EMAIL and COC_PASSWORD environment variables are not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG environment variable is not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_clan(normalize_tag(CLAN_TAG))

    try:
        clan = run_async(_fetch())

        location = None
        if clan.location:
            location = {
                "id": clan.location.id,
                "name": clan.location.name,
                "is_country": clan.location.is_country,
                "country_code": getattr(clan.location, "country_code", None)
            }

        districts = clan.capital_districts or []
        capital_hall_level = None
        for d in districts:
            if d.name.lower() == "capital peak":
                capital_hall_level = d.hall_level
                break

        clan_capital = {
            "capital_hall_level": capital_hall_level,
            "districts": [
                {"name": d.name, "district_hall_level": d.hall_level}
                for d in districts
            ],
        }

        data = {
            "name": clan.name,
            "tag": clan.tag,
            "level": clan.level,
            "description": clan.description,
            "points": clan.points,
            "war_frequency": str(clan.war_frequency) if clan.war_frequency else None,
            "member_count": clan.member_count,
            "location": location,
            "type": str(clan.type) if clan.type else None,
            "required_trophies": clan.required_trophies,
            "war_wins": clan.war_wins,
            "war_losses": clan.war_losses,
            "war_ties": clan.war_ties,
            "war_win_streak": clan.war_win_streak,
            "is_war_log_public": clan.public_war_log,
            "badge_url": clan.badge.large if clan.badge else None,
            "clan_capital": clan_capital,
        }
        return jsonify(data)
    except coc.NotFound:
        return error_response(f"Clan '{CLAN_TAG}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid Clash of Clans credentials", 401)
    except Exception as e:
        logger.exception("Error fetching clan")
        return error_response(str(e))


@app.route("/clan/members", methods=["GET"])
def get_clan_members():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("COC_EMAIL and COC_PASSWORD environment variables are not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG environment variable is not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_members(normalize_tag(CLAN_TAG))

    try:
        members = run_async(_fetch())

        data = []
        for m in members:
            last_seen = None
            if hasattr(m, "last_seen") and m.last_seen:
                try:
                    last_seen = m.last_seen.isoformat()
                except Exception:
                    last_seen = str(m.last_seen)

            data.append({
                "name": m.name,
                "tag": m.tag,
                "role": str(m.role) if m.role else None,
                "town_hall_level": m.town_hall,
                "trophies": m.trophies,
                "builder_base_trophies": m.builder_base_trophies,
                "donations": m.donations,
                "donations_received": m.received,
                "last_seen": last_seen,
                "war_opted_in": getattr(m, "war_opted_in", None),
                "league": str(m.league) if getattr(m, "league", None) else None,
            })

        return jsonify(data)
    except coc.NotFound:
        return error_response(f"Clan '{CLAN_TAG}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid Clash of Clans credentials", 401)
    except Exception as e:
        logger.exception("Error fetching clan members")
        return error_response(str(e))


@app.route("/clan/currentwar", methods=["GET"])
def get_current_war():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("COC_EMAIL and COC_PASSWORD environment variables are not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG environment variable is not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_current_war(normalize_tag(CLAN_TAG))

    try:
        war = run_async(_fetch())

        if war is None or str(war.state) == "notInWar":
            return jsonify({"state": "notInWar"})

        def serialize_attacks(attacks):
            result = []
            for a in (attacks or []):
                result.append({
                    "attacker_tag": a.attacker_tag,
                    "defender_tag": a.defender_tag,
                    "stars": a.stars,
                    "destruction": a.destruction,
                    "order": a.order,
                })
            return result

        def serialize_war_members(members):
            result = []
            for m in (members or []):
                result.append({
                    "name": m.name,
                    "tag": m.tag,
                    "town_hall_level": m.town_hall,
                    "map_position": m.map_position,
                    "attacks": serialize_attacks(m.attacks),
                    "best_opponent_attack": {
                        "attacker_tag": m.best_opponent_attack.attacker_tag,
                        "stars": m.best_opponent_attack.stars,
                        "destruction": m.best_opponent_attack.destruction,
                    } if m.best_opponent_attack else None,
                })
            return result

        data = {
            "state": str(war.state),
            "team_size": war.team_size,
            "attacks_per_member": war.attacks_per_member,
            "start_time": war.start_time.time.isoformat() if war.start_time else None,
            "end_time": war.end_time.time.isoformat() if war.end_time else None,
            "clan": {
                "name": war.clan.name,
                "tag": war.clan.tag,
                "stars": war.clan.stars,
                "destruction": war.clan.destruction,
                "attacks_used": war.clan.attacks_used,
                "members": serialize_war_members(war.clan.members),
            },
            "opponent": {
                "name": war.opponent.name,
                "tag": war.opponent.tag,
                "stars": war.opponent.stars,
                "destruction": war.opponent.destruction,
                "attacks_used": war.opponent.attacks_used,
                "members": serialize_war_members(war.opponent.members),
            },
        }
        return jsonify(data)
    except coc.PrivateWarLog:
        return error_response("War log is private for this clan", 403)
    except coc.NotFound:
        return error_response(f"Clan '{CLAN_TAG}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid Clash of Clans credentials", 401)
    except Exception as e:
        logger.exception("Error fetching current war")
        return error_response(str(e))


@app.route("/clan/warlog", methods=["GET"])
def get_war_log():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("COC_EMAIL and COC_PASSWORD environment variables are not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG environment variable is not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_war_log(normalize_tag(CLAN_TAG), limit=20)

    try:
        wars = run_async(_fetch())

        data = []
        for war in wars:
            end_time = None
            if war.end_time:
                try:
                    end_time = war.end_time.time.isoformat()
                except Exception:
                    end_time = str(war.end_time)

            entry = {
                "result": str(war.result) if war.result else None,
                "end_time": end_time,
                "team_size": war.team_size,
                "attacks_per_member": war.attacks_per_member,
                "clan": {
                    "name": war.clan.name if war.clan else None,
                    "tag": war.clan.tag if war.clan else None,
                    "stars": war.clan.stars if war.clan else None,
                    "destruction": war.clan.destruction if war.clan else None,
                    "attacks_used": war.clan.attacks_used if war.clan else None,
                    "exp_earned": getattr(war.clan, "exp_earned", None) if war.clan else None,
                },
                "opponent": {
                    "name": war.opponent.name if war.opponent else None,
                    "tag": war.opponent.tag if war.opponent else None,
                    "stars": war.opponent.stars if war.opponent else None,
                    "destruction": war.opponent.destruction if war.opponent else None,
                    "attacks_used": war.opponent.attacks_used if war.opponent else None,
                },
            }
            data.append(entry)

        return jsonify(data)
    except coc.PrivateWarLog:
        return error_response("War log is private for this clan", 403)
    except coc.NotFound:
        return error_response(f"Clan '{CLAN_TAG}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid Clash of Clans credentials", 401)
    except Exception as e:
        logger.exception("Error fetching war log")
        return error_response(str(e))


@app.route("/clan/capitalraidseasons", methods=["GET"])
def get_capital_raid_seasons():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("COC_EMAIL and COC_PASSWORD environment variables are not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG environment variable is not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_raid_log(normalize_tag(CLAN_TAG), limit=10)

    try:
        seasons = run_async(_fetch())

        data = []
        for season in seasons:
            members_data = []
            members_attacked = set()

            for member in (season.members or []):
                attack_count = getattr(member, "attack_count", 0) or 0
                capital_resources_looted = getattr(member, "capital_resources_looted", 0) or 0
                tag = getattr(member, "tag", None)
                if tag and attack_count > 0:
                    members_attacked.add(tag)
                members_data.append({
                    "name": getattr(member, "name", None),
                    "tag": tag,
                    "attack_count": attack_count,
                    "capital_resources_looted": capital_resources_looted,
                    "attacked": attack_count > 0,
                })

            not_attacked = [m for m in members_data if m["tag"] not in members_attacked]

            districts_data = []
            for district in (season.attack_log or []):
                district_entries = []
                for d in (getattr(district, "districts", None) or []):
                    district_entries.append({
                        "name": getattr(d, "name", None),
                        "id": getattr(d, "id", None),
                        "destruction_percent": getattr(d, "destruction_percent", None),
                        "stars": getattr(d, "stars", None),
                        "attack_count": getattr(d, "attack_count", None),
                        "total_loot": getattr(d, "total_loot", None),
                    })
                districts_data.append({
                    "opponent_name": getattr(district, "name", None),
                    "opponent_tag": getattr(district, "tag", None),
                    "districts": district_entries,
                })

            start_time = None
            end_time = None
            try:
                if season.start_time:
                    start_time = season.start_time.time.isoformat()
            except Exception:
                start_time = str(season.start_time) if season.start_time else None
            try:
                if season.end_time:
                    end_time = season.end_time.time.isoformat()
            except Exception:
                end_time = str(season.end_time) if season.end_time else None

            data.append({
                "state": str(season.state) if season.state else None,
                "start_time": start_time,
                "end_time": end_time,
                "total_loot": season.total_loot,
                "offensive_reward": getattr(season, "offensive_reward", None),
                "defensive_reward": getattr(season, "defensive_reward", None),
                "raids_completed": getattr(season, "completed_raid_count", None),
                "total_attacks": getattr(season, "total_attack_count", None),
                "enemy_districts_destroyed": getattr(season, "enemy_districts_destroyed", None),
                "members": members_data,
                "members_not_attacked": not_attacked,
                "attack_log": districts_data,
            })

        return jsonify(data)
    except coc.NotFound:
        return error_response(f"Clan '{CLAN_TAG}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid Clash of Clans credentials", 401)
    except Exception as e:
        logger.exception("Error fetching capital raid seasons")
        return error_response(str(e))


@app.route("/player/<path:tag>", methods=["GET"])
def get_player(tag):
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("COC_EMAIL and COC_PASSWORD environment variables are not set", 503)

    normalized = normalize_tag(tag)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_player(normalized)

    try:
        player = run_async(_fetch())

        def serialize_troops(troops):
            result = []
            for t in (troops or []):
                result.append({
                    "name": t.name,
                    "level": t.level,
                    "max_level": t.max_level,
                    "village": str(t.village) if hasattr(t, "village") else None,
                })
            return result

        def serialize_heroes(heroes):
            result = []
            for h in (heroes or []):
                equipment = []
                for eq in (getattr(h, "equipment", None) or []):
                    equipment.append({
                        "name": eq.name,
                        "level": eq.level,
                        "max_level": eq.max_level,
                    })
                result.append({
                    "name": h.name,
                    "level": h.level,
                    "max_level": h.max_level,
                    "village": str(h.village) if hasattr(h, "village") else None,
                    "equipment": equipment,
                })
            return result

        def serialize_spells(spells):
            result = []
            for s in (spells or []):
                result.append({
                    "name": s.name,
                    "level": s.level,
                    "max_level": s.max_level,
                    "village": str(s.village) if hasattr(s, "village") else None,
                })
            return result

        def serialize_achievements(achievements):
            result = []
            for a in (achievements or []):
                result.append({
                    "name": a.name,
                    "stars": a.stars,
                    "value": a.value,
                    "target": a.target,
                    "info": a.info,
                    "village": str(a.village) if hasattr(a, "village") else None,
                })
            return result

        def serialize_pets(pets):
            result = []
            for p in (pets or []):
                result.append({
                    "name": p.name,
                    "level": p.level,
                    "max_level": p.max_level,
                    "village": str(p.village) if hasattr(p, "village") else None,
                })
            return result

        def serialize_legend_season(season):
            if season is None:
                return None
            return {
                "id": getattr(season, "id", None),
                "rank": getattr(season, "rank", None),
                "trophies": getattr(season, "trophies", None),
            }

        clan_info = None
        if player.clan:
            clan_info = {
                "name": player.clan.name,
                "tag": player.clan.tag,
                "level": player.clan.level,
                "badge_url": player.clan.badge.large if player.clan.badge else None,
            }

        league_info = None
        if getattr(player, "league", None):
            league_info = {
                "id": player.league.id,
                "name": player.league.name,
                "icon_url": player.league.icon.medium if player.league.icon else None,
            }

        legend_stats = player.legend_statistics
        legend_statistics = None
        if legend_stats:
            legend_statistics = {
                "legend_trophies": getattr(legend_stats, "legend_trophies", None),
                "current_season": serialize_legend_season(getattr(legend_stats, "current_season", None)),
                "previous_season": serialize_legend_season(getattr(legend_stats, "previous_season", None)),
                "best_season": serialize_legend_season(getattr(legend_stats, "best_season", None)),
            }

        home_heroes = [h for h in (player.heroes or []) if not h.is_builder_base]
        builder_heroes = [h for h in (player.heroes or []) if h.is_builder_base]

        data = {
            "name": player.name,
            "tag": player.tag,
            "town_hall_level": player.town_hall,
            "town_hall_weapon_level": player.town_hall_weapon,
            "exp_level": player.exp_level,
            "trophies": player.trophies,
            "best_trophies": player.best_trophies,
            "war_stars": player.war_stars,
            "attack_wins": player.attack_wins,
            "defense_wins": player.defense_wins,
            "builder_hall_level": player.builder_hall,
            "builder_base_trophies": player.builder_base_trophies,
            "best_builder_base_trophies": player.best_builder_base_trophies,
            "versus_battle_wins": getattr(player, "versus_attack_wins", None),
            "role": str(player.role) if player.role else None,
            "war_opted_in": getattr(player, "war_opted_in", None),
            "donations": player.donations,
            "donations_received": player.received,
            "clan": clan_info,
            "league": league_info,
            "legend_statistics": legend_statistics,
            "troops": serialize_troops(player.home_troops),
            "heroes": serialize_heroes(home_heroes),
            "builder_base_heroes": serialize_heroes(builder_heroes),
            "spells": serialize_spells(player.spells),
            "siege_machines": serialize_troops(player.siege_machines),
            "pets": serialize_pets(player.pets),
            "super_troops": serialize_troops(player.super_troops),
            "builder_base_troops": serialize_troops(player.builder_troops),
            "achievements": serialize_achievements(player.achievements),
        }
        return jsonify(data)
    except coc.NotFound:
        return error_response(f"Player '{tag}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid Clash of Clans credentials", 401)
    except Exception as e:
        logger.exception("Error fetching player")
        return error_response(str(e))


def keep_alive():
    while True:
        time.sleep(300)
        logger.info("Keep-alive ping at %s", datetime.utcnow().isoformat())


if __name__ == "__main__":
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    logger.info("Starting Clash of Clans REST API on port 5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
