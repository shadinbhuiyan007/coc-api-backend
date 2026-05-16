import os
import asyncio
import logging
import threading
import time
import urllib.parse
from datetime import datetime

import aiohttp
from flask import Flask, jsonify
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins="*")

COC_EMAIL = "mehadishadin007@gmail.com"
COC_PASSWORD = "23241893$$Ss"
CLAN_TAG = "GVUPYPLC"

COC_DEV_URL = "https://developer.clashofclans.com"
COC_API_URL = "https://api.clashofclans.com/v1"

_api_key = None
_api_key_lock = threading.Lock()

# Super troop names — সব super troops এর নাম
SUPER_TROOP_NAMES = {
    "Super Barbarian", "Super Archer", "Super Giant", "Sneaky Goblin",
    "Super Wall Breaker", "Rocket Balloon", "Inferno Dragon", "Super Witch",
    "Ice Hound", "Super Bowler", "Super Dragon", "Super Minion",
    "Super Valkyrie", "Super Witch", "Super Hog Rider", "Super Miner",
    "Super Hound", "Super P.E.K.K.A", "Super Yeti", "Super Lava Hound",
    "Super Goblin", "Super Wizard", "Super Archer", "Flying Fortress",
}

# Siege machine names — সব siege machines এর নাম
SIEGE_MACHINE_NAMES = {
    "Wall Wrecker", "Battle Blimp", "Stone Slammer", "Siege Barracks",
    "Log Launcher", "Flame Flinger", "Battle Drill", "Troop Launcher",
    "Sky Wagon",
}

# Pet names — সব pets এর নাম
PET_NAMES = {
    "L.A.S.S.I", "Electro Owl", "Mighty Yak", "Unicorn",
    "Frosty", "Diggy", "Poison Lizard", "Phoenix",
    "Spirit Fox", "Angry Jelly", "Sneezy", "Greedy Raven",
}


def normalize_tag(tag):
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag.upper().strip()


def error_response(message, status=500):
    return jsonify({"error": message}), status


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


async def get_current_ip():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.ipify.org?format=json",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                return data.get("ip")
    except Exception as e:
        logger.error(f"Failed to get IP: {e}")
        return None


async def login_and_get_key():
    global _api_key
    current_ip = await get_current_ip()
    if not current_ip:
        raise Exception("Could not get current server IP")
    logger.info(f"Server IP: {current_ip}")

    jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        async with session.post(
            f"{COC_DEV_URL}/api/login",
            json={"email": COC_EMAIL, "password": COC_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Login failed {resp.status}: {text}")
            logger.info("Logged in to developer portal")

        async with session.post(
            f"{COC_DEV_URL}/api/apikey/list",
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            keys_data = await resp.json()
            existing_keys = keys_data.get("keys", [])

        valid_key = None
        keys_to_revoke = []
        for k in existing_keys:
            cidr = k.get("cidrRanges", [])
            if current_ip in cidr or f"{current_ip}/32" in cidr:
                valid_key = k.get("key")
                logger.info("Reusing existing key for current IP")
                break
            else:
                keys_to_revoke.append(k.get("id"))

        if not valid_key:
            if len(existing_keys) >= 10:
                for kid in keys_to_revoke[:6]:
                    try:
                        await session.post(
                            f"{COC_DEV_URL}/api/apikey/revoke",
                            json={"id": kid},
                            headers={"Content-Type": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=10)
                        )
                    except Exception:
                        pass

            async with session.post(
                f"{COC_DEV_URL}/api/apikey/create",
                json={
                    "name": "CoC-Stats-App",
                    "description": "Auto key for CoC stats app",
                    "cidrRanges": [current_ip],
                    "scopes": ["clash"]
                },
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                create_data = await resp.json()
                valid_key = create_data.get("key", {}).get("key")
                logger.info("Created new API key")

        if not valid_key:
            raise Exception("Could not obtain API key")

        with _api_key_lock:
            _api_key = valid_key
        return valid_key


async def get_api_key():
    global _api_key
    with _api_key_lock:
        if _api_key:
            return _api_key
    return await login_and_get_key()


async def coc_request(endpoint, params=None):
    key = await get_api_key()
    url = f"{COC_API_URL}/{endpoint}"
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, headers=headers, params=params,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 403:
                global _api_key
                with _api_key_lock:
                    _api_key = None
                new_key = await login_and_get_key()
                headers["Authorization"] = f"Bearer {new_key}"
                async with session.get(
                    url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as r2:
                    if r2.status == 200:
                        return await r2.json()
                    elif r2.status == 404:
                        return None
                    else:
                        raise Exception(f"API error: {r2.status}")
            elif resp.status == 404:
                return None
            else:
                text = await resp.text()
                raise Exception(f"API {resp.status}: {text}")


def build_clan(raw):
    loc = raw.get("location") or {}
    capital = raw.get("clanCapital") or {}
    districts = capital.get("districts", [])
    cap_hall = None
    for d in districts:
        if (d.get("name") or "").lower() == "capital peak":
            cap_hall = d.get("districtHallLevel")
            break
    return {
        "name": raw.get("name"),
        "tag": raw.get("tag"),
        "level": raw.get("clanLevel"),
        "description": raw.get("description"),
        "points": raw.get("clanPoints", 0),
        "war_frequency": raw.get("warFrequency"),
        "member_count": raw.get("members", 0),
        "location": {
            "id": loc.get("id"),
            "name": loc.get("name"),
            "is_country": loc.get("isCountry"),
            "country_code": loc.get("countryCode"),
        } if loc else None,
        "type": raw.get("type"),
        "required_trophies": raw.get("requiredTrophies", 0),
        "war_wins": raw.get("warWins", 0),
        "war_losses": raw.get("warLosses", 0),
        "war_ties": raw.get("warTies", 0),
        "war_win_streak": raw.get("warWinStreak", 0),
        "is_war_log_public": raw.get("isWarLogPublic"),
        "badge_url": (raw.get("badgeUrls") or {}).get("large"),
        "clan_capital": {
            "capital_hall_level": cap_hall,
            "districts": [
                {"name": d.get("name"), "district_hall_level": d.get("districtHallLevel")}
                for d in districts
            ]
        }
    }


def build_member(m):
    league = m.get("league") or {}
    return {
        "name": m.get("name"),
        "tag": m.get("tag"),
        "role": m.get("role"),
        "town_hall_level": m.get("townHallLevel"),
        "exp_level": m.get("expLevel"),
        "builder_hall_level": m.get("builderHallLevel"),
        "trophies": m.get("trophies", 0),
        "builder_base_trophies": m.get("builderBaseTrophies", 0),
        "donations": m.get("donations", 0),
        "donations_received": m.get("donationsReceived", 0),
        "last_seen": m.get("lastSeen"),
        "war_opted_in": m.get("warPreference") == "in",
        "league": league.get("name") if league else None,
        "league_icon_url": (league.get("iconUrls") or {}).get("medium") if league else None,
    }


def build_player(p):
    # League — নতুন rank system সহ সব
    league = p.get("league") or {}
    league_info = {
        "id": league.get("id"),
        "name": league.get("name"),
        "icon_url": (league.get("iconUrls") or {}).get("medium"),
    } if league else None

    # Clan
    clan = p.get("clan") or {}
    clan_info = {
        "name": clan.get("name"),
        "tag": clan.get("tag"),
        "level": clan.get("clanLevel"),
        "badge_url": (clan.get("badgeUrls") or {}).get("large"),
    } if clan else None

    # Heroes + Equipment
    home_heroes, builder_heroes = [], []
    for h in p.get("heroes", []):
        equipment = [
            {
                "name": eq.get("name"),
                "level": eq.get("level", 0),
                "max_level": eq.get("maxLevel", 0),
            }
            for eq in h.get("equipment", [])
        ]
        hero = {
            "name": h.get("name"),
            "level": h.get("level", 0),
            "max_level": h.get("maxLevel", 0),
            "village": h.get("village", "home"),
            "equipment": equipment,
        }
        if h.get("village") == "builderBase":
            builder_heroes.append(hero)
        else:
            home_heroes.append(hero)

    # Troops — API তে সব একসাথে আসে
    # super troops, siege machines, pets আলাদা করতে হবে
    home_troops = []
    super_troops = []
    siege_machines = []
    pets = []

    for t in p.get("troops", []):
        name = t.get("name", "")
        item = {
            "name": name,
            "level": t.get("level", 0),
            "max_level": t.get("maxLevel", 0),
            "village": t.get("village", "home"),
        }
        if name in PET_NAMES:
            pets.append(item)
        elif name in SIEGE_MACHINE_NAMES:
            siege_machines.append(item)
        elif name in SUPER_TROOP_NAMES or t.get("superTroopIsActive", False):
            super_troops.append(item)
        elif t.get("village") == "home":
            home_troops.append(item)

    # Builder troops
    builder_troops = [
        {
            "name": t.get("name"),
            "level": t.get("level", 0),
            "max_level": t.get("maxLevel", 0),
            "village": "builderBase",
        }
        for t in p.get("troops", [])
        if t.get("village") == "builderBase"
    ]

    # Spells
    spells = [
        {
            "name": s.get("name"),
            "level": s.get("level", 0),
            "max_level": s.get("maxLevel", 0),
            "village": s.get("village", "home"),
        }
        for s in p.get("spells", [])
    ]

    # Achievements
    achievements = [
        {
            "name": a.get("name"),
            "stars": a.get("stars", 0),
            "value": a.get("value", 0),
            "target": a.get("target", 0),
            "info": a.get("info"),
            "village": a.get("village", "home"),
        }
        for a in p.get("achievements", [])
    ]

    # Legend statistics
    ls = p.get("legendStatistics") or {}
    legend_statistics = None
    if ls:
        def parse_season(s):
            return {
                "id": s.get("id"),
                "rank": s.get("rank"),
                "trophies": s.get("trophies")
            } if s else None
        legend_statistics = {
            "legend_trophies": ls.get("legendTrophies"),
            "current_season": parse_season(ls.get("currentSeason")),
            "previous_season": parse_season(ls.get("previousSeason")),
            "best_season": parse_season(ls.get("bestSeason")),
        }

    return {
        "name": p.get("name"),
        "tag": p.get("tag"),
        "town_hall_level": p.get("townHallLevel"),
        "town_hall_weapon_level": p.get("townHallWeaponLevel"),
        "exp_level": p.get("expLevel"),
        "trophies": p.get("trophies", 0),
        "best_trophies": p.get("bestTrophies", 0),
        "war_stars": p.get("warStars", 0),
        "attack_wins": p.get("attackWins", 0),
        "defense_wins": p.get("defenseWins", 0),
        "builder_hall_level": p.get("builderHallLevel"),
        "builder_base_trophies": p.get("builderBaseTrophies", 0),
        "best_builder_base_trophies": p.get("bestBuilderBaseTrophies", 0),
        "versus_battle_wins": p.get("versusBattleWins"),
        "role": p.get("role"),
        "war_opted_in": p.get("warPreference") == "in",
        "donations": p.get("donations", 0),
        "donations_received": p.get("donationsReceived", 0),
        "clan": clan_info,
        "league": league_info,
        "legend_statistics": legend_statistics,
        "troops": home_troops,
        "heroes": home_heroes,
        "builder_base_heroes": builder_heroes,
        "spells": spells,
        "siege_machines": siege_machines,
        "pets": pets,
        "super_troops": super_troops,
        "builder_base_troops": builder_troops,
        "achievements": achievements,
    }


@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "CoC Stats API - Direct Mode"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "clan_tag": CLAN_TAG,
        "api_key_ready": _api_key is not None,
    })


@app.route("/clan", methods=["GET"])
def get_clan():
    try:
        tag = urllib.parse.quote(normalize_tag(CLAN_TAG))
        data = run_async(coc_request(f"clans/{tag}"))
        if not data:
            return error_response("Clan not found", 404)
        return jsonify(build_clan(data))
    except Exception as e:
        logger.exception("Error fetching clan")
        return error_response(str(e))


@app.route("/clan/members", methods=["GET"])
def get_clan_members():
    try:
        tag = urllib.parse.quote(normalize_tag(CLAN_TAG))
        data = run_async(coc_request(f"clans/{tag}/members"))
        if not data:
            return error_response("Clan not found", 404)
        return jsonify([build_member(m) for m in data.get("items", [])])
    except Exception as e:
        logger.exception("Error fetching members")
        return error_response(str(e))


@app.route("/clan/search/<path:tag>", methods=["GET"])
def search_clan(tag):
    try:
        enc = urllib.parse.quote(normalize_tag(tag))
        data = run_async(coc_request(f"clans/{enc}"))
        if not data:
            return error_response(f"Clan '{tag}' not found", 404)
        return jsonify(build_clan(data))
    except Exception as e:
        logger.exception("Error searching clan")
        return error_response(str(e))


@app.route("/clan/search/<path:tag>/members", methods=["GET"])
def search_clan_members(tag):
    try:
        enc = urllib.parse.quote(normalize_tag(tag))
        data = run_async(coc_request(f"clans/{enc}/members"))
        if not data:
            return error_response(f"Clan '{tag}' not found", 404)
        return jsonify([build_member(m) for m in data.get("items", [])])
    except Exception as e:
        logger.exception("Error searching clan members")
        return error_response(str(e))


@app.route("/clan/currentwar", methods=["GET"])
def get_current_war():
    try:
        tag = urllib.parse.quote(normalize_tag(CLAN_TAG))
        war = run_async(coc_request(f"clans/{tag}/currentwar"))
        if not war or war.get("state") == "notInWar":
            return jsonify({"state": "notInWar"})

        def attacks(lst):
            return [{
                "attacker_tag": a.get("attackerTag"),
                "defender_tag": a.get("defenderTag"),
                "stars": a.get("stars", 0),
                "destruction": a.get("destructionPercentage", 0),
                "order": a.get("order", 0),
            } for a in (lst or [])]

        def members(lst):
            result = []
            for m in (lst or []):
                bo = m.get("bestOpponentAttack")
                result.append({
                    "name": m.get("name"),
                    "tag": m.get("tag"),
                    "town_hall_level": m.get("townhallLevel"),
                    "map_position": m.get("mapPosition"),
                    "attacks": attacks(m.get("attacks", [])),
                    "best_opponent_attack": {
                        "attacker_tag": bo.get("attackerTag"),
                        "stars": bo.get("stars", 0),
                        "destruction": bo.get("destructionPercentage", 0),
                    } if bo else None,
                })
            return result

        def side(key):
            s = war.get(key, {})
            return {
                "name": s.get("name"),
                "tag": s.get("tag"),
                "stars": s.get("stars", 0),
                "destruction": s.get("destructionPercentage", 0),
                "attacks_used": s.get("attacks", 0),
                "members": members(s.get("members", [])),
            }

        return jsonify({
            "state": war.get("state"),
            "team_size": war.get("teamSize"),
            "attacks_per_member": war.get("attacksPerMember"),
            "start_time": war.get("startTime"),
            "end_time": war.get("endTime"),
            "clan": side("clan"),
            "opponent": side("opponent"),
        })
    except Exception as e:
        logger.exception("Error fetching current war")
        return error_response(str(e))


@app.route("/clan/warlog", methods=["GET"])
def get_war_log():
    try:
        tag = urllib.parse.quote(normalize_tag(CLAN_TAG))
        data = run_async(coc_request(f"clans/{tag}/warlog", {"limit": 20}))
        if not data:
            return jsonify([])
        wars = []
        for w in data.get("items", []):
            def side(key):
                s = w.get(key, {})
                return {
                    "name": s.get("name"),
                    "tag": s.get("tag"),
                    "stars": s.get("stars", 0),
                    "destruction": s.get("destructionPercentage", 0),
                    "attacks_used": s.get("attacks", 0),
                    "exp_earned": s.get("expEarned"),
                }
            wars.append({
                "result": w.get("result"),
                "end_time": w.get("endTime"),
                "team_size": w.get("teamSize"),
                "attacks_per_member": w.get("attacksPerMember"),
                "clan": side("clan"),
                "opponent": side("opponent"),
            })
        return jsonify(wars)
    except Exception as e:
        logger.exception("Error fetching war log")
        return error_response(str(e))


@app.route("/clan/capitalraidseasons", methods=["GET"])
def get_capital_raid_seasons():
    try:
        tag = urllib.parse.quote(normalize_tag(CLAN_TAG))
        data = run_async(coc_request(f"clans/{tag}/capitalraidseasons", {"limit": 10}))
        if not data:
            return jsonify([])
        seasons = []
        for season in data.get("items", []):
            members_data = []
            attacked = set()
            for m in season.get("members", []):
                cnt = m.get("attacks", 0)
                t = m.get("tag")
                if t and cnt > 0:
                    attacked.add(t)
                members_data.append({
                    "name": m.get("name"),
                    "tag": t,
                    "attack_count": cnt,
                    "capital_resources_looted": m.get("capitalResourcesLooted", 0),
                    "attacked": cnt > 0,
                })
            not_attacked = [m for m in members_data if m.get("tag") not in attacked]
            attack_log = []
            for raid in season.get("attackLog", []):
                defender = raid.get("defender", {})
                districts = [{
                    "name": d.get("name"),
                    "id": d.get("id"),
                    "destruction_percent": d.get("destructionPercent"),
                    "stars": d.get("stars"),
                    "attack_count": d.get("attackCount"),
                    "total_loot": d.get("totalLooted"),
                } for d in raid.get("districts", [])]
                attack_log.append({
                    "opponent_name": defender.get("name"),
                    "opponent_tag": defender.get("tag"),
                    "districts": districts,
                })
            seasons.append({
                "state": season.get("state"),
                "start_time": season.get("startTime"),
                "end_time": season.get("endTime"),
                "total_loot": season.get("capitalTotalLoot", 0),
                "offensive_reward": season.get("offensiveReward"),
                "defensive_reward": season.get("defensiveReward"),
                "raids_completed": season.get("raidsCompleted"),
                "total_attacks": season.get("totalAttacks"),
                "enemy_districts_destroyed": season.get("enemyDistrictsDestroyed"),
                "members": members_data,
                "members_not_attacked": not_attacked,
                "attack_log": attack_log,
            })
        return jsonify(seasons)
    except Exception as e:
        logger.exception("Error fetching raid seasons")
        return error_response(str(e))


@app.route("/player/<path:tag>", methods=["GET"])
def get_player(tag):
    try:
        enc = urllib.parse.quote(normalize_tag(tag))
        data = run_async(coc_request(f"players/{enc}"))
        if not data:
            return error_response(f"Player '{tag}' not found", 404)
        return jsonify(build_player(data))
    except Exception as e:
        logger.exception("Error fetching player")
        return error_response(str(e))


def keep_alive():
    while True:
        time.sleep(300)
        logger.info("Keep-alive at %s", datetime.utcnow().isoformat())


def init_key():
    try:
        run_async(login_and_get_key())
        logger.info("API key initialized")
    except Exception as e:
        logger.error(f"Key init failed: {e}")


if __name__ == "__main__":
    threading.Thread(target=init_key, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    logger.info("Starting CoC Stats API - Direct Mode")
    app.run(host="0.0.0.0", port=5000, debug=False)
