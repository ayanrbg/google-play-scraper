"""Brand detection: big publishers, traffic-buying (hyper/hybrid-casual) publishers, franchise IP,
plus automatic signals from the developer's portfolio.

A game's growth is useless as an idea signal when it comes from an existing brand
or a paid-UA machine - these get flags the radar filters on.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select

from gpi.models import BrandRule

BIG_DEV_INSTALLS = 50_000_000   # another game of this developer passed this -> established studio
BIG_PORTFOLIO = 40              # apps on the developer page

FLAG_LABELS = {
    "major": "Крупный издатель",
    "hc_publisher": "Паблишер гиперказуала (закупка трафика)",
    "franchise": "Франшиза / бренд",
    "big_dev": "У студии уже есть хит 50M+",
    "big_portfolio": "Большой портфель (40+ приложений)",
    "cash": "Игра на деньги (выплаты, призы)",
}
RULE_KINDS = ["major", "hc_publisher", "franchise", "cash", "cash_text"]

DEFAULT_RULES: dict[str, list[str]] = {
    "major": [
        "Supercell", "King", "Playrix", "Tencent", "NetEase", "miHoYo", "HoYoverse", "COGNOSPHERE",
        "Electronic Arts", "ELECTRONIC ARTS", "Activision", "Ubisoft", "Zynga", "2K", "Take-Two",
        "Scopely", "Moon Active", "Playtika", "Niantic", "Nintendo", "SEGA", "Bandai Namco",
        "SQUARE ENIX", "KONAMI", "CAPCOM", "Netmarble", "NCSOFT", "NEXON", "KRAFTON", "Com2uS",
        "Garena", "Moonton", "Lilith", "FunPlus", "37GAMES", "IGG", "Roblox", "Mojang", "Microsoft",
        "Epic Games", "Riot Games", "Blizzard", "Gameloft", "Warner Bros", "Disney", "Sony",
        "Level Infinite", "Yostar", "KURO", "Devsisters", "Kakao Games", "Dream Games", "Peak Games",
        "Rovio", "Outfit7", "Miniclip", "Wildlife Studios", "Jam City", "Glu", "Product Madness",
        "Huuuge", "Aristocrat", "DoubleDown", "SciPlay", "Big Fish", "Hutch", "NaturalMotion",
        "Kabam", "Nexters", "Plarium", "Habby", "Century Games", "Tap4fun", "StarUnion",
        "Hypergryph", "Papergames", "bilibili", "Perfect World", "Seasun", "Playdemic", "Socialpoint",
        "Small Giant", "SYBO", "Space Ape", "Pixonic", "MY.GAMES",
        "Unico Studio", "Magic Tavern", "Playstudios", "Machine Zone", "Snail Games",
        "Netflix", "Hasbro", "Mattel", "LEGO", "Nexon", "Smilegate", "Pearl Abyss", "Webzen",
        "Wemade", "Gravity", "Shift Up", "Neowiz", "Gamevil", "Joycity", "Longtu", "Yoozoo",
        "Elex", "Camel Games", "Topwar", "River Game", "Pocket Gems", "Kiloo", "Halfbrick",
    ],
    "hc_publisher": [
        "VOODOO", "SayGames", "Azur Games", "AZUR GAMES", "Rollic", "Supersonic Studios",
        "Homa Games", "CrazyLabs", "TabTale", "Lion Studios", "Kwalee", "Ketchapp", "Good Job Games",
        "Ruby Games", "Moonee", "Amanotes", "iKame", "ABI Global", "ABI Games", "Onesoft", "Yso Corp",
        "BoomBit", "Madbox", "Tapnation", "Mondo Games", "Gamejam", "JoyPac", "Popcore", "Freeplay",
        "Magic Games", "Bravestars", "Falcon Game Studio", "Higgs Studio", "Zego Studio", "Hwqgames",
        "Casual Azur", "Neon Play", "Crazy Labs", "Hungry Studio", "Fomo Games", "Gybe Games",
        "Burny Games", "Loop Games", "Ducky", "Kayac", "Playducky", "Estoty", "Green Panda Games",
        "Clue Hive", "Rocket Game Studio", "Tapped", "Weegoon", "Alictus", "Tiramisu", "Playgendary",
    ],
    "franchise": [
        "Pokémon", "Pokemon", "Marvel", "Disney", "Pixar", "Star Wars", "Harry Potter", "Minecraft",
        "Roblox", "Sonic", "Mario", "Naruto", "Dragon Ball", "One Piece", "Bleach", "Jujutsu Kaisen",
        "Demon Slayer", "Attack on Titan", "Gundam", "Evangelion", "Final Fantasy", "Dragon Quest",
        "Monster Hunter", "Resident Evil", "Street Fighter", "Mortal Kombat", "Call of Duty",
        "Battlefield", "Rainbow Six", "Assassin's Creed", "The Division", "Far Cry", "Warhammer",
        "Lord of the Rings", "Game of Thrones", "Walking Dead", "Transformers", "LEGO", "Barbie",
        "Hello Kitty", "Peppa Pig", "PAW Patrol", "SpongeBob", "Looney Tunes", "Batman", "Superman",
        "Spider-Man", "Avengers", "Jurassic", "Fast & Furious", "Monopoly", "Scrabble", "UNO",
        "Tetris", "PAC-MAN", "Angry Birds", "Subway Surfers", "Candy Crush", "Clash of Clans",
        "Clash Royale", "Talking Tom", "Hello Neighbor", "Five Nights at Freddy", "Poppy Playtime",
        "Among Us", "FIFA", "EA SPORTS", "NBA", "NFL", "WWE", "UFC", "Formula 1", "MotoGP", "Asphalt",
        "Need for Speed", "Grand Theft Auto", "GTA", "Genshin", "Honkai", "Arknights", "Sanrio",
        "Squid Game", "Stranger Things", "Sesame Street", "CoComelon", "Bluey", "Garfield", "Smurfs",
        "Tom and Jerry", "Shrek", "Minions", "Despicable Me", "Kung Fu Panda", "Ghostbusters",
        "Godzilla", "The Sims", "Tomb Raider", "Hitman", "Metal Slug", "Tekken", "Solo Leveling",
        "Chainsaw Man", "Hunter x Hunter", "Sailor Moon", "Yu-Gi-Oh", "Digimon", "Beyblade",
        "Hot Wheels", "Crash Bandicoot", "Rayman", "Plants vs. Zombies", "Cut the Rope", "Fruit Ninja",
        "Temple Run", "Hill Climb Racing", "Geometry Dash", "Stumble Guys", "Brawl Stars",
        "Free Fire", "PUBG", "Fortnite", "Apex Legends", "Valorant", "League of Legends", "Overwatch",
        "Diablo", "Hearthstone", "Warcraft", "StarCraft", "Mobile Legends", "Honor of Kings",
        "Toca Boca", "My Talking", "Hatsune Miku",
    ],
    # "Play and get paid" games: growth is bought with payout promises, not an idea signal.
    # Matched as whole words in the title.
    "cash": [
        "cash", "prize", "prizes", "paypal", "earn", "payout", "giveaway", "sweepstakes",
        "tap money", "win money", "real money", "free money", "money rewards", "win rewards",
        "earn rewards", "get rewards", "dinheiro", "dinero", "uang", "деньги", "para kazan",
    ],
    # Matched in the title or the short description: only unambiguous phrases, because
    # tycoon games say "earn cash to upgrade" and are not cash games.
    "cash_text": [
        "real money", "real cash", "win real", "cash out", "cashout", "cash prizes", "cash prize",
        "paypal", "gift card", "gift cards", "withdraw", "withdrawal", "get paid", "earn money online",
        "make money", "dinheiro real", "dinero real", "uang asli", "saldo dana",
    ],
}


def _words(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(r"(?<![\w])" + re.escape(p) + r"(?![\w])", re.IGNORECASE) for p in patterns]


@dataclass
class Rules:
    major: list[str]
    hc_publisher: list[str]
    franchise: list[re.Pattern]
    cash_title: list[re.Pattern]
    cash_text: list[re.Pattern]

    @classmethod
    def load(cls, session) -> "Rules":
        rows = session.execute(select(BrandRule.kind, BrandRule.pattern)).all()
        by_kind: dict[str, list[str]] = {k: [] for k in RULE_KINDS}
        for kind, pattern in rows:
            by_kind.setdefault(kind, []).append(pattern)
        return cls(
            major=[p.lower() for p in by_kind["major"]],
            hc_publisher=[p.lower() for p in by_kind["hc_publisher"]],
            franchise=_words(by_kind["franchise"]),
            cash_title=_words(by_kind["cash"]),
            cash_text=_words(by_kind["cash_text"]),
        )


def _dev_match(developer: str | None, developer_id: str | None, patterns: list[str]) -> bool:
    if not developer and not developer_id:
        return False
    hay = f"{developer or ''}\n{developer_id or ''}".lower()
    for p in patterns:
        # Short patterns ("King", "2K", "IGG") must match a whole word, not a substring.
        if len(p) <= 4:
            if re.search(r"(?<![\w])" + re.escape(p) + r"(?![\w])", hay):
                return True
        elif p in hay:
            return True
    return False


def classify(title: str | None, developer: str | None, developer_id: str | None,
             dev_other_max_installs: int | None, dev_app_count: int | None, rules: Rules,
             summary: str | None = None) -> list[str]:
    flags = []
    if _dev_match(developer, developer_id, rules.major):
        flags.append("major")
    if _dev_match(developer, developer_id, rules.hc_publisher):
        flags.append("hc_publisher")
    if title and any(p.search(title) for p in rules.franchise):
        flags.append("franchise")
    if dev_other_max_installs and dev_other_max_installs >= BIG_DEV_INSTALLS:
        flags.append("big_dev")
    if dev_app_count and dev_app_count >= BIG_PORTFOLIO:
        flags.append("big_portfolio")
    text = f"{title or ''}\n{summary or ''}"
    if (title and any(p.search(title) for p in rules.cash_title)) or any(p.search(text) for p in rules.cash_text):
        flags.append("cash")
    return flags


def seed_rules(session) -> int:
    existing = set(session.execute(select(BrandRule.kind, BrandRule.pattern)).all())
    added = 0
    for kind, patterns in DEFAULT_RULES.items():
        for p in dict.fromkeys(patterns):
            if (kind, p) not in existing:
                session.add(BrandRule(kind=kind, pattern=p, note="default"))
                existing.add((kind, p))
                added += 1
    return added
