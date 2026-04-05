import os
import asyncio
import logging
import threading
import time
import urllib.parse
from datetime import datetime

import aiohttp
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


def serialize_member(m):
    last_seen = None
    if hasattr(m, "last_seen") and m.last_seen:
        try:
            last_seen = m.last_seen.isoformat()
        except Exception:
            last_seen = str(m.last_seen)

    league_icon = None
    try:
        if getattr(m, "league", None) and m.league.icon:
            league_icon = m.league.icon.medium
    except Exception:
        pass

    return {
        "name": m.name,
        "tag": m.tag,
        "role": str(m.role) if m.role else None,
        "town_hall_level": getattr(m, "town_hall", None),
        "exp_level": getattr(m, "exp_level", None),
        "builder_hall_level": getattr(m, "builder_hall", None),
        "trophies": getattr(m, "trophies", 0),
        "builder_base_trophies": getattr(m, "builder_base_trophies", 0),
        "donations": getattr(m, "donations", 0),
        "donations_received": getattr(m, "received", 0),
        "last_seen": last_seen,
        "war_opted_in": getattr(m, "war_opted_in", None),
        "league": str(m.league) if getattr(m, "league", None) else None,
        "league_icon_url": league_icon,
    }


def build_clan_data(clan):
    location = None
    if clan.location:
        location = {
            "id": clan.location.id,
            "name": clan.location.name,
            "is_country": getattr(clan.location, "is_country", None),
            "country_code": getattr(clan.location, "country_code", None)
        }

    districts = getattr(clan, "capital_districts", None) or []
    capital_hall_level = None
    for d in districts:
        if getattr(d, "name", "").lower() == "capital peak":
            capital_hall_level = getattr(d, "hall_level", None)
            break

    clan_capital = {
        "capital_hall_level": capital_hall_level,
        "districts": [
            {"name": getattr(d, "name", None), "district_hall_level": getattr(d, "hall_level", None)}
            for d in districts
        ],
    }

    badge_url = None
    try:
        if clan.badge:
            badge_url = clan.badge.large
    except Exception:
        pass

    return {
        "name": clan.name,
        "tag": clan.tag,
        "level": getattr(clan, "level", None),
        "description": getattr(clan, "description", None),
        "points": getattr(clan, "points", 0),
        "war_frequency": str(clan.war_frequency) if getattr(clan, "war_frequency", None) else None,
        "member_count": getattr(clan, "member_count", 0),
        "location": location,
        "type": str(clan.type) if getattr(clan, "type", None) else None,
        "required_trophies": getattr(clan, "required_trophies", 0),
        "war_wins": getattr(clan, "war_wins", 0),
        "war_losses": getattr(clan, "war_losses", 0),
        "war_ties": getattr(clan, "war_ties", 0),
        "war_win_streak": getattr(clan, "war_win_streak", 0),
        "is_war_log_public": getattr(clan, "public_war_log", None),
        "badge_url": badge_url,
        "clan_capital": clan_capital,
    }


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
        return error_response("Credentials not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_clan(normalize_tag(CLAN_TAG))

    try:
        clan = run_async(_fetch())
        return jsonify(build_clan_data(clan))
    except coc.NotFound:
        return error_response(f"Clan not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
    except Exception as e:
        logger.exception("Error fetching clan")
        return error_response(str(e))


@app.route("/clan/members", methods=["GET"])
def get_clan_members():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("Credentials not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_members(normalize_tag(CLAN_TAG))

    try:
        members = run_async(_fetch())
        return jsonify([serialize_member(m) for m in members])
    except coc.NotFound:
        return error_response("Clan not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
    except Exception as e:
        logger.exception("Error fetching members")
        return error_response(str(e))


@app.route("/clan/search/<path:tag>", methods=["GET"])
def search_clan(tag):
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("Credentials not set", 503)

    normalized = normalize_tag(tag)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_clan(normalized)

    try:
        clan = run_async(_fetch())
        return jsonify(build_clan_data(clan))
    except coc.NotFound:
        return error_response(f"Clan '{tag}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
    except Exception as e:
        logger.exception("Error fetching clan by tag")
        return error_response(str(e))


@app.route("/clan/search/<path:tag>/members", methods=["GET"])
def search_clan_members(tag):
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("Credentials not set", 503)

    normalized = normalize_tag(tag)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_members(normalized)

    try:
        members = run_async(_fetch())
        return jsonify([serialize_member(m) for m in members])
    except coc.NotFound:
        return error_response(f"Clan '{tag}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
    except Exception as e:
        logger.exception("Error fetching clan members by tag")
        return error_response(str(e))


@app.route("/clan/currentwar", methods=["GET"])
def get_current_war():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("Credentials not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG not set", 503)

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
                try:
                    result.append({
                        "attacker_tag": getattr(a, "attacker_tag", None),
                        "defender_tag": getattr(a, "defender_tag", None),
                        "stars": getattr(a, "stars", 0),
                        "destruction": getattr(a, "destruction", 0),
                        "order": getattr(a, "order", 0),
                    })
                except Exception:
                    pass
            return result

        def serialize_war_members(members):
            result = []
            for m in (members or []):
                try:
                    best_opp = None
                    if getattr(m, "best_opponent_attack", None):
                        best_opp = {
                            "attacker_tag": getattr(m.best_opponent_attack, "attacker_tag", None),
                            "stars": getattr(m.best_opponent_attack, "stars", 0),
                            "destruction": getattr(m.best_opponent_attack, "destruction", 0),
                        }
                    result.append({
                        "name": m.name,
                        "tag": m.tag,
                        "town_hall_level": getattr(m, "town_hall", None),
                        "map_position": getattr(m, "map_position", None),
                        "attacks": serialize_attacks(getattr(m, "attacks", [])),
                        "best_opponent_attack": best_opp,
                    })
                except Exception:
                    pass
            return result

        data = {
            "state": str(war.state),
            "team_size": getattr(war, "team_size", None),
            "attacks_per_member": getattr(war, "attacks_per_member", None),
            "start_time": war.start_time.time.isoformat() if getattr(war, "start_time", None) else None,
            "end_time": war.end_time.time.isoformat() if getattr(war, "end_time", None) else None,
            "clan": {
                "name": getattr(war.clan, "name", None),
                "tag": getattr(war.clan, "tag", None),
                "stars": getattr(war.clan, "stars", 0),
                "destruction": getattr(war.clan, "destruction", 0),
                "attacks_used": getattr(war.clan, "attacks_used", 0),
                "members": serialize_war_members(getattr(war.clan, "members", [])),
            },
            "opponent": {
                "name": getattr(war.opponent, "name", None),
                "tag": getattr(war.opponent, "tag", None),
                "stars": getattr(war.opponent, "stars", 0),
                "destruction": getattr(war.opponent, "destruction", 0),
                "attacks_used": getattr(war.opponent, "attacks_used", 0),
                "members": serialize_war_members(getattr(war.opponent, "members", [])),
            },
        }
        return jsonify(data)
    except coc.PrivateWarLog:
        return error_response("War log is private", 403)
    except coc.NotFound:
        return error_response("Clan not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
    except Exception as e:
        logger.exception("Error fetching current war")
        return error_response(str(e))


@app.route("/clan/warlog", methods=["GET"])
def get_war_log():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("Credentials not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_war_log(normalize_tag(CLAN_TAG), limit=20)

    try:
        wars = run_async(_fetch())

        data = []
        for war in wars:
            try:
                end_time = None
                if getattr(war, "end_time", None):
                    try:
                        end_time = war.end_time.time.isoformat()
                    except Exception:
                        end_time = str(war.end_time)

                entry = {
                    "result": str(war.result) if getattr(war, "result", None) else None,
                    "end_time": end_time,
                    "team_size": getattr(war, "team_size", None),
                    "attacks_per_member": getattr(war, "attacks_per_member", None),
                    "clan": {
                        "name": getattr(war.clan, "name", None) if war.clan else None,
                        "tag": getattr(war.clan, "tag", None) if war.clan else None,
                        "stars": getattr(war.clan, "stars", 0) if war.clan else 0,
                        "destruction": getattr(war.clan, "destruction", 0) if war.clan else 0,
                        "attacks_used": getattr(war.clan, "attacks_used", 0) if war.clan else 0,
                        "exp_earned": getattr(war.clan, "exp_earned", None) if war.clan else None,
                    },
                    "opponent": {
                        "name": getattr(war.opponent, "name", None) if war.opponent else None,
                        "tag": getattr(war.opponent, "tag", None) if war.opponent else None,
                        "stars": getattr(war.opponent, "stars", 0) if war.opponent else 0,
                        "destruction": getattr(war.opponent, "destruction", 0) if war.opponent else 0,
                        "attacks_used": getattr(war.opponent, "attacks_used", 0) if war.opponent else 0,
                    },
                }
                data.append(entry)
            except Exception:
                pass

        return jsonify(data)
    except coc.PrivateWarLog:
        return error_response("War log is private", 403)
    except coc.NotFound:
        return error_response("Clan not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
    except Exception as e:
        logger.exception("Error fetching war log")
        return error_response(str(e))


@app.route("/clan/capitalraidseasons", methods=["GET"])
def get_capital_raid_seasons():
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("Credentials not set", 503)
    if not CLAN_TAG:
        return error_response("CLAN_TAG not set", 503)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            return await client.get_raid_log(normalize_tag(CLAN_TAG), limit=10)

    try:
        seasons = run_async(_fetch())

        data = []
        for season in seasons:
            try:
                members_data = []
                members_attacked = set()

                for member in (getattr(season, "members", None) or []):
                    try:
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
                    except Exception:
                        pass

                not_attacked = [m for m in members_data if m.get("tag") not in members_attacked]

                districts_data = []
                for district in (getattr(season, "attack_log", None) or []):
                    try:
                        district_entries = []
                        for d in (getattr(district, "districts", None) or []):
                            try:
                                district_entries.append({
                                    "name": getattr(d, "name", None),
                                    "id": getattr(d, "id", None),
                                    "destruction_percent": getattr(d, "destruction_percent", None),
                                    "stars": getattr(d, "stars", None),
                                    "attack_count": getattr(d, "attack_count", None),
                                    "total_loot": getattr(d, "total_loot", None),
                                })
                            except Exception:
                                pass
                        districts_data.append({
                            "opponent_name": getattr(district, "name", None),
                            "opponent_tag": getattr(district, "tag", None),
                            "districts": district_entries,
                        })
                    except Exception:
                        pass

                start_time = None
                end_time = None
                try:
                    if getattr(season, "start_time", None):
                        start_time = season.start_time.time.isoformat()
                except Exception:
                    start_time = str(season.start_time) if getattr(season, "start_time", None) else None
                try:
                    if getattr(season, "end_time", None):
                        end_time = season.end_time.time.isoformat()
                except Exception:
                    end_time = str(season.end_time) if getattr(season, "end_time", None) else None

                data.append({
                    "state": str(season.state) if getattr(season, "state", None) else None,
                    "start_time": start_time,
                    "end_time": end_time,
                    "total_loot": getattr(season, "total_loot", 0),
                    "offensive_reward": getattr(season, "offensive_reward", None),
                    "defensive_reward": getattr(season, "defensive_reward", None),
                    "raids_completed": getattr(season, "completed_raid_count", None),
                    "total_attacks": getattr(season, "total_attack_count", None),
                    "enemy_districts_destroyed": getattr(season, "enemy_districts_destroyed", None),
                    "members": members_data,
                    "members_not_attacked": not_attacked,
                    "attack_log": districts_data,
                })
            except Exception:
                pass

        return jsonify(data)
    except coc.NotFound:
        return error_response("Clan not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
    except Exception as e:
        logger.exception("Error fetching capital raid seasons")
        return error_response(str(e))


@app.route("/player/<path:tag>", methods=["GET"])
def get_player(tag):
    if not COC_EMAIL or not COC_PASSWORD:
        return error_response("Credentials not set", 503)

    normalized = normalize_tag(tag)

    async def _fetch():
        async with coc.Client() as client:
            await client.login(COC_EMAIL, COC_PASSWORD)
            player = await client.get_player(normalized)

            raw_heroes = []
            try:
                api_key_str = None
                keys = getattr(client.http, '_keys', [])
                if not keys:
                    keys = getattr(client.http, 'keys', [])
                if keys:
                    key_obj = keys[0]
                    if isinstance(key_obj, str):
                        api_key_str = key_obj
                    else:
                        api_key_str = (
                            getattr(key_obj, 'key', None) or
                            getattr(key_obj, 'token', None) or
                            getattr(key_obj, '_key', None) or
                            str(key_obj)
                        )

                if api_key_str and len(api_key_str) > 10:
                    encoded_tag = urllib.parse.quote(normalized)
                    url = f"https://api.clashofclans.com/v1/players/{encoded_tag}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers={"Authorization": f"Bearer {api_key_str}"}) as resp:
                            if resp.status == 200:
                                raw_data = await resp.json()
                                raw_heroes = raw_data.get("heroes", [])
            except Exception as e:
                logger.warning(f"Direct API call failed: {e}")

            return player, raw_heroes

    try:
        player, raw_heroes = run_async(_fetch())

        def safe_serialize_troops(troops):
            result = []
            for t in (troops or []):
                try:
                    result.append({
                        "name": getattr(t, "name", None),
                        "level": getattr(t, "level", 0),
                        "max_level": getattr(t, "max_level", 0),
                        "village": str(t.village) if hasattr(t, "village") else None,
                    })
                except Exception:
                    pass
            return result

        def safe_serialize_heroes(heroes):
            result = []
            for h in (heroes or []):
                try:
                    equipment = []
                    for eq in (getattr(h, "equipment", None) or []):
                        try:
                            equipment.append({
                                "name": getattr(eq, "name", None),
                                "level": getattr(eq, "level", 0),
                                "max_level": getattr(eq, "max_level", 0),
                            })
                        except Exception:
                            pass
                    result.append({
                        "name": getattr(h, "name", None),
                        "level": getattr(h, "level", 0),
                        "max_level": getattr(h, "max_level", 0),
                        "village": str(h.village) if hasattr(h, "village") else None,
                        "equipment": equipment,
                    })
                except Exception:
                    pass
            return result

        def safe_serialize_spells(spells):
            result = []
            for s in (spells or []):
                try:
                    result.append({
                        "name": getattr(s, "name", None),
                        "level": getattr(s, "level", 0),
                        "max_level": getattr(s, "max_level", 0),
                        "village": str(s.village) if hasattr(s, "village") else None,
                    })
                except Exception:
                    pass
            return result

        def safe_serialize_achievements(achievements):
            result = []
            for a in (achievements or []):
                try:
                    result.append({
                        "name": getattr(a, "name", None),
                        "stars": getattr(a, "stars", 0),
                        "value": getattr(a, "value", 0),
                        "target": getattr(a, "target", 0),
                        "info": getattr(a, "info", None),
                        "village": str(a.village) if hasattr(a, "village") else None,
                    })
                except Exception:
                    pass
            return result

        def safe_serialize_pets(pets):
            result = []
            for p in (pets or []):
                try:
                    result.append({
                        "name": getattr(p, "name", None),
                        "level": getattr(p, "level", 0),
                        "max_level": getattr(p, "max_level", 0),
                        "village": str(p.village) if hasattr(p, "village") else None,
                    })
                except Exception:
                    pass
            return result

        def safe_serialize_legend_season(season):
            if season is None:
                return None
            try:
                return {
                    "id": getattr(season, "id", None),
                    "rank": getattr(season, "rank", None),
                    "trophies": getattr(season, "trophies", None),
                }
            except Exception:
                return None

        # Safe clan info
        clan_info = None
        try:
            if player.clan:
                badge_url = None
                try:
                    badge_url = player.clan.badge.large
                except Exception:
                    pass
                clan_info = {
                    "name": getattr(player.clan, "name", None),
                    "tag": getattr(player.clan, "tag", None),
                    "level": getattr(player.clan, "level", None),
                    "badge_url": badge_url,
                }
        except Exception:
            pass

        # Safe league info
        league_info = None
        try:
            if getattr(player, "league", None):
                icon_url = None
                try:
                    icon_url = player.league.icon.medium
                except Exception:
                    pass
                league_info = {
                    "id": getattr(player.league, "id", None),
                    "name": getattr(player.league, "name", None),
                    "icon_url": icon_url,
                }
        except Exception:
            pass

        # Safe legend statistics
        legend_statistics = None
        try:
            legend_stats = player.legend_statistics
            if legend_stats:
                legend_statistics = {
                    "legend_trophies": getattr(legend_stats, "legend_trophies", None),
                    "current_season": safe_serialize_legend_season(getattr(legend_stats, "current_season", None)),
                    "previous_season": safe_serialize_legend_season(getattr(legend_stats, "previous_season", None)),
                    "best_season": safe_serialize_legend_season(getattr(legend_stats, "best_season", None)),
                }
        except Exception:
            pass

        # Safe hero separation
        home_heroes = []
        builder_heroes = []
        try:
            for h in (getattr(player, "heroes", None) or []):
                try:
                    if getattr(h, "is_builder_base", False):
                        builder_heroes.append(h)
                    else:
                        home_heroes.append(h)
                except Exception:
                    home_heroes.append(h)
        except Exception:
            pass

        serialized_home_heroes = safe_serialize_heroes(home_heroes)
        serialized_builder_heroes = safe_serialize_heroes(builder_heroes)

        # Add missing heroes from direct API call (e.g. Dragon Duke)
        try:
            known_names = {h["name"] for h in serialized_home_heroes + serialized_builder_heroes}
            for rh in raw_heroes:
                if rh.get("name") not in known_names:
                    entry = {
                        "name": rh.get("name"),
                        "level": rh.get("level", 0),
                        "max_level": rh.get("maxLevel", 0),
                        "village": rh.get("village", "home"),
                        "equipment": [],
                    }
                    if rh.get("village") == "builderBase":
                        serialized_builder_heroes.append(entry)
                    else:
                        serialized_home_heroes.append(entry)
        except Exception:
            pass

        # Safe troop getters
        home_troops = []
        try:
            home_troops = getattr(player, "home_troops", None) or []
        except Exception:
            try:
                home_troops = [t for t in (getattr(player, "troops", None) or [])
                               if getattr(t, "village", "") != "builderBase"]
            except Exception:
                pass

        builder_troops = []
        try:
            builder_troops = getattr(player, "builder_troops", None) or []
        except Exception:
            try:
                builder_troops = [t for t in (getattr(player, "troops", None) or [])
                                  if getattr(t, "village", "") == "builderBase"]
            except Exception:
                pass

        siege_machines = []
        try:
            siege_machines = getattr(player, "siege_machines", None) or []
        except Exception:
            pass

        super_troops = []
        try:
            super_troops = getattr(player, "super_troops", None) or []
        except Exception:
            pass

        pets = []
        try:
            pets = getattr(player, "pets", None) or []
        except Exception:
            pass

        spells = []
        try:
            spells = getattr(player, "spells", None) or []
        except Exception:
            pass

        achievements = []
        try:
            achievements = getattr(player, "achievements", None) or []
        except Exception:
            pass

        data = {
            "name": player.name,
            "tag": player.tag,
            "town_hall_level": getattr(player, "town_hall", None),
            "town_hall_weapon_level": getattr(player, "town_hall_weapon", None),
            "exp_level": getattr(player, "exp_level", None),
            "trophies": getattr(player, "trophies", 0),
            "best_trophies": getattr(player, "best_trophies", 0),
            "war_stars": getattr(player, "war_stars", 0),
            "attack_wins": getattr(player, "attack_wins", 0),
            "defense_wins": getattr(player, "defense_wins", 0),
            "builder_hall_level": getattr(player, "builder_hall", None),
            "builder_base_trophies": getattr(player, "builder_base_trophies", 0),
            "best_builder_base_trophies": getattr(player, "best_builder_base_trophies", 0),
            "versus_battle_wins": getattr(player, "versus_attack_wins", None),
            "role": str(player.role) if getattr(player, "role", None) else None,
            "war_opted_in": getattr(player, "war_opted_in", None),
            "donations": getattr(player, "donations", 0),
            "donations_received": getattr(player, "received", 0),
            "clan": clan_info,
            "league": league_info,
            "legend_statistics": legend_statistics,
            "troops": safe_serialize_troops(home_troops),
            "heroes": serialized_home_heroes,
            "builder_base_heroes": serialized_builder_heroes,
            "spells": safe_serialize_spells(spells),
            "siege_machines": safe_serialize_troops(siege_machines),
            "pets": safe_serialize_pets(pets),
            "super_troops": safe_serialize_troops(super_troops),
            "builder_base_troops": safe_serialize_troops(builder_troops),
            "achievements": safe_serialize_achievements(achievements),
        }
        return jsonify(data)
    except coc.NotFound:
        return error_response(f"Player '{tag}' not found", 404)
    except coc.InvalidCredentials:
        return error_response("Invalid credentials", 401)
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
