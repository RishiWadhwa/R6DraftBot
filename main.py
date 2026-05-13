import discord
from discord.ext import commands
from itertools import combinations
import random
import json
import os

# ── Config ──────────────────────────────────────────────────────────────────

RANK_WEIGHTS = {
    "unranked": 1,
    "copper":   1,
    "bronze":   2,
    "silver":   3,
    "iron": 3,
    "gold":     4,
    "platinum": 5,
    "plat": 5,
    "diamond":  6,
    "champ":    7,
    "champion": 7
}

RANK_DISPLAY = {
    "unranked": "Unranked",
    "copper":   "Copper",
    "bronze":   "Bronze",
    "silver":   "Silver",
    "iron": "Silver",
    "gold":     "Gold",
    "platinum": "Platinum",
    "plat": "Platinum",
    "diamond":  "Diamond",
    "champ":    "Champion",
    "champion": "Champion"
}

CONFIG_FILE = "blipbot_config.json"  # stores admin role IDs per guild
MIN_PLAYERS = 4
MATCH_SIZE  = 10  # max players selected per match

# ── Persistence helpers ──────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ── Bot setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# guild_id → { user_id: { "name": str, "rank": str, "weight": int } }
signup_pools = {}

# guild_id → admin role ID (int)
admin_roles = load_config()

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_pool(guild_id):
    return signup_pools.setdefault(str(guild_id), {})

def is_admin_player(member, guild_id):
    role_id = admin_roles.get(str(guild_id))
    if role_id is None:
        return False
    return any(r.id == role_id for r in member.roles)

def best_split(players):
    """
    Given a list of (name, weight, rank) tuples, return the most balanced
    (team_a, team_b) split. For odd counts the larger team gets the split
    that minimises the score difference (the heavier side naturally absorbs
    the extra body via the optimiser).
    """
    n = len(players)
    size_a = n // 2 + (n % 2)   # larger half goes to team A
    size_b = n // 2

    best_diff  = float("inf")
    best_combo = None

    for combo in combinations(range(n), size_a):
        team_a = [players[i] for i in combo]
        team_b = [players[i] for i in range(n) if i not in combo]
        diff = abs(sum(p[1] for p in team_a) - sum(p[1] for p in team_b))
        if diff < best_diff:
            best_diff  = diff
            best_combo = (team_a, team_b)

    return best_combo, best_diff

def format_team(label, players):
    total = sum(p[1] for p in players)
    lines = [f"**{label}** — Rating: {total}"]
    for name, weight, rank in sorted(players, key=lambda p: -p[1]):
        lines.append(f"  • {name} ({RANK_DISPLAY[rank]})")
    return "\n".join(lines)

# ── Commands ─────────────────────────────────────────────────────────────────

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setadmin(ctx, role: discord.Role):
    """Designate which role gets guaranteed selection (if signed up)."""
    admin_roles[str(ctx.guild.id)] = role.id
    save_config(admin_roles)
    await ctx.send(f"✅ **{role.name}** is now the guaranteed-selection role.")

@bot.command()
async def signup(ctx, rank: str = None):
    """Sign up for the next custom match. Usage: !signup [rank]"""
    if rank is None:
        await ctx.send(
            "❌ Please include your rank. Example: `!signup gold`\n"
            f"Valid ranks: {', '.join(RANK_DISPLAY.values())}"
        )
        return

    rank = rank.lower()
    if rank not in RANK_WEIGHTS:
        await ctx.send(
            f"❌ **{rank}** isn't a valid rank.\n"
            f"Valid ranks: {', '.join(RANK_DISPLAY.values())}"
        )
        return

    pool = get_pool(ctx.guild.id)
    uid  = str(ctx.author.id)
    already_in = uid in pool
    pool[uid] = {
        "name":   ctx.author.display_name,
        "rank":   rank,
        "weight": RANK_WEIGHTS[rank],
    }

    verb = "updated their rank to" if already_in else "signed up as"
    await ctx.send(
        f"{'🔄' if already_in else '✅'} **{ctx.author.display_name}** {verb} "
        f"**{RANK_DISPLAY[rank]}**. ({len(pool)} in pool)"
    )

@bot.command()
async def signout(ctx):
    """Remove yourself from the signup pool."""
    pool = get_pool(ctx.guild.id)
    uid  = str(ctx.author.id)
    if uid not in pool:
        await ctx.send("❌ You're not currently signed up.")
        return
    del pool[uid]
    await ctx.send(f"👋 **{ctx.author.display_name}** has been removed from the pool. ({len(pool)} remaining)")

@bot.command()
async def pool(ctx):
    """Show everyone currently signed up."""
    players = list(get_pool(ctx.guild.id).values())
    if not players:
        await ctx.send("📋 The signup pool is empty.")
        return

    sorted_players = sorted(players, key=lambda p: -p["weight"])
    lines = [f"📋 **Signup Pool** ({len(players)} players)\n"]
    for p in sorted_players:
        lines.append(f"  • {p['name']} — {RANK_DISPLAY[p['rank']]}")
    await ctx.send("\n".join(lines))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def consign(ctx, member: discord.Member, rank: str = None):
    """Sign up another player by mention. Usage: !consign @player [rank]"""
    if rank is None:
        await ctx.send(
            "❌ Please include a rank. Example: `!consign @player gold`\n"
            f"Valid ranks: {', '.join(RANK_DISPLAY.values())}"
        )
        return

    rank = rank.lower()
    if rank not in RANK_WEIGHTS:
        await ctx.send(
            f"❌ **{rank}** isn't a valid rank.\n"
            f"Valid ranks: {', '.join(RANK_DISPLAY.values())}"
        )
        return

    pool = get_pool(ctx.guild.id)
    uid  = str(member.id)
    already_in = uid in pool
    pool[uid] = {
        "name":   member.display_name,
        "rank":   rank,
        "weight": RANK_WEIGHTS[rank],
    }

    verb = "updated to" if already_in else "signed up as"
    await ctx.send(
        f"{'🔄' if already_in else '✅'} **{member.display_name}** was {verb} "
        f"**{RANK_DISPLAY[rank]}** by {ctx.author.display_name}. ({len(pool)} in pool)"
    )

@consign.error
async def consign_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need the **Manage Server** permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Please mention a valid server member. Example: `!consign @player gold`")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def maketeams(ctx):
    """Randomly select up to 10 players (admins guaranteed) and balance teams."""
    pool      = get_pool(ctx.guild.id)
    guild_id  = str(ctx.guild.id)
    role_id   = admin_roles.get(guild_id)

    if len(pool) < MIN_PLAYERS:
        await ctx.send(f"❌ Need at least {MIN_PLAYERS} players to make teams. Currently have {len(pool)}.")
        return

    # Separate admin-role players from regular players
    admin_players   = []
    regular_players = []

    for uid, data in pool.items():
        member = ctx.guild.get_member(int(uid))
        if member and role_id and any(r.id == role_id for r in member.roles):
            admin_players.append((uid, data))
        else:
            regular_players.append((uid, data))

    # Fill remaining slots randomly from regular players
    slots_remaining = max(0, MATCH_SIZE - len(admin_players))
    random.shuffle(regular_players)

    selected_regular  = regular_players[:slots_remaining]
    benched_regular   = regular_players[slots_remaining:]

    selected = admin_players + selected_regular

    # Build player tuples for the algorithm: (name, weight, rank)
    player_tuples = [
        (d["name"], d["weight"], d["rank"])
        for _, d in selected
    ]

    (team_a, team_b), diff = best_split(player_tuples)

    # ── Output ───────────────────────────────────────────────────────────────
    msg_parts = [
        "🎮 **Teams are set!**\n",
        format_team("⚔️  Team Alpha", team_a),
        "",
        format_team("🛡️  Team Bravo", team_b),
        "",
        f"*Rating difference: {diff}*",
    ]

    if benched_regular:
        benched_names = ", ".join(d["name"] for _, d in benched_regular)
        msg_parts += [
            "",
            f"⏳ **Not selected this round** (still in pool): {benched_names}",
        ]

    await ctx.send("\n".join(msg_parts))

@maketeams.error
async def maketeams_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need the **Manage Server** permission to use this command.")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def clearpool(ctx):
    """Clear the entire signup pool. Requires manage_guild permission."""
    signup_pools[str(ctx.guild.id)] = {}
    await ctx.send("🗑️ Signup pool cleared.")

@clearpool.error
async def clearpool_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need the **Manage Server** permission to use this command.")

@bot.command(name="help", aliases=["commands"])
async def help_command(ctx):
    """Show all available commands."""
    embed = discord.Embed(
        title="😎 BlipBot Commands",
        description="Mixing up fair teams for fair R6 customs!",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="📝 Signup",
        value=(
            "`!signup [rank]` — Sign up for the next match\n"
            "Valid ranks: `copper`, `bronze`, `silver`, `gold`, `platinum`, `diamond`, `champ`\n"
            "`!signout` — Remove yourself from the pool"
        ),
        inline=False
    )
    embed.add_field(
        name="🎮 Match",
        value=(
            "`!pool` — See everyone currently signed up"
        ),
        inline=False
    )
    embed.add_field(
        name="🔧 Admin (Manage Server only)",
        value=(
            "`!consign @player [rank]` — Sign up another player on their behalf\n"
            "`!maketeams` — Randomly select up to 10 players and generate balanced teams\n"
            "`!clearpool` — Clear the entire signup pool\n"
            "`!setadmin @role` — Set the role that gets guaranteed selection if signed up"
        ),
        inline=False
    )
    embed.set_footer(text="Guaranteed players are selected first, remaining slots filled randomly.")
    await ctx.send(embed=embed)

# ── Error handling ────────────────────────────────────────────────────────────

@setadmin.error
async def setadmin_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need the **Manage Server** permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Please mention a valid role. Example: `!setadmin @Streamer`")

@bot.event
async def on_ready():
    print(f"✅ BlipBot is online as {bot.user}")
    activity = discord.CustomActivity(name="😎 Mixing up fair teams for fair R6 customs")
    await bot.change_presence(status=discord.Status.idle, activity=activity)

# ── Run ───────────────────────────────────────────────────────────────────────
# Replace the string below with your bot token, or load it from an env variable:
import os; 
bot.run(os.environ["DISCORD_TOKEN"])

# bot.run("YOUR_BOT_TOKEN_HERE")