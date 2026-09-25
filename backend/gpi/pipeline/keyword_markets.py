"""Keyword markets: language + store country, with seed words and autocomplete suffixes.

Autocomplete and search are language-specific, so each market has its own seed vocabulary
(genre/mechanic words the way players type them) and its own alphabet for "seed + letter"
expansion. The English market also learns seeds from titles of fresh hits.
"""

from dataclasses import dataclass, field
import string

LATIN = list(string.ascii_lowercase)
CYRILLIC = list("абвгдежзиклмнопрстуфхцчшэюя")
TURKISH = LATIN + list("çğıöşü")
# First syllables of the kana rows / hangul initials - what a player types next in Japanese / Korean
KANA = ["あ", "か", "さ", "た", "な", "は", "ま", "や", "ら", "わ", "ア", "カ", "サ", "タ", "マ"]
HANGUL = ["가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하"]

EN_SEEDS = [
    "puzzle", "sort", "merge", "match", "block", "tile", "idle", "tycoon", "simulator", "survival",
    "zombie", "shooter", "racing", "car", "parking", "drift", "truck", "bus", "city", "farm",
    "cooking", "restaurant", "cafe", "hotel", "hospital", "school", "makeover", "dress up",
    "fashion", "hair", "nail", "baby", "pet", "cat", "dog", "horse", "dinosaur", "dragon", "monster",
    "robot", "ninja", "knight", "magic", "tower defense", "castle", "kingdom", "war", "army",
    "battle", "arena", "io", "snake", "ball", "run", "jump", "stack", "color", "paint", "draw",
    "coloring", "word", "crossword", "trivia", "quiz", "math", "brain", "logic", "escape",
    "hidden object", "mystery", "horror", "scary", "prank", "asmr", "satisfying", "relax", "fidget",
    "slime", "cake", "candy", "fruit", "water", "screw", "nuts bolts", "jam", "traffic", "hexa",
    "2048", "solitaire", "mahjong", "sudoku", "chess", "domino", "bingo", "ludo", "dice",
    "fishing", "hunting", "sniper", "gun", "plane", "train", "ship", "tank", "mining", "craft",
    "building", "sandbox", "open world", "obby", "parkour", "stickman", "ragdoll", "physics",
    "car crash", "mech", "space", "pirate", "fish", "ocean", "garden", "home design", "house",
    "decor", "cleaning", "wash", "repair", "doctor", "dentist", "clicker", "roguelike", "rpg",
    "anime", "gacha", "card battle", "auto battler", "survivor", "platformer", "runner", "arcade",
    "pixel", "offline games", "games for kids", "2 player games", "multiplayer", "simulator games",
]


@dataclass
class Market:
    lang: str
    country: str
    label: str
    seeds: list[str]
    suffixes: list[str] = field(default_factory=lambda: LATIN)
    primary: bool = False   # bigger daily budget, learns seeds from hit titles


MARKETS: list[Market] = [
    Market("en", "us", "English · США", EN_SEEDS, primary=True),
    Market("es", "mx", "Español · Мексика", [
        "juego de", "rompecabezas", "carros", "coches", "motos", "camiones", "autobus", "estacionar",
        "cocina", "restaurante", "granja", "zombies", "disparos", "guerra", "futbol", "simulador",
        "construir", "ciudad", "moda", "vestir", "maquillaje", "bebe", "mascota", "gato", "perro",
        "caballo", "dinosaurio", "dragon", "terror", "escape", "palabras", "sopa de letras", "trivia",
        "matematicas", "colorear", "pintar", "dibujar", "carreras", "pesca", "sin internet",
        "para niños", "de 2 jugadores", "ordenar", "combinar", "idle",
    ]),
    Market("pt", "br", "Português · Бразилия", [
        "jogo de", "quebra cabeça", "carro", "moto", "caminhão", "ônibus", "estacionar", "culinária",
        "cozinhar", "restaurante", "fazenda", "zumbi", "tiro", "guerra", "futebol", "simulador",
        "construir", "cidade", "moda", "vestir", "maquiagem", "bebê", "pet", "gato", "cachorro",
        "cavalo", "dinossauro", "dragão", "terror", "fuga", "palavras", "caça palavras", "quiz",
        "matemática", "colorir", "pintar", "desenhar", "corrida", "pesca", "offline",
        "para crianças", "2 jogadores", "ordenar", "juntar", "idle",
    ]),
    Market("id", "id", "Bahasa · Индонезия", [
        "game", "puzzle", "mobil", "motor", "truk", "bus", "parkir", "masak", "restoran", "kebun",
        "zombie", "tembak", "perang", "sepak bola", "simulator", "bangun", "kota", "dandan", "rias",
        "bayi", "kucing", "anjing", "kuda", "dinosaurus", "naga", "horor", "kabur", "kata",
        "teka teki", "kuis", "matematika", "mewarnai", "menggambar", "balap", "mancing", "offline",
        "anak", "2 pemain", "bus simulator", "idle",
    ]),
    Market("ru", "ru", "Русский · Россия", [
        "игра", "головоломка", "машины", "машинки", "мотоцикл", "грузовик", "автобус", "парковка",
        "готовка", "кухня", "ресторан", "ферма", "зомби", "стрелялки", "война", "футбол", "симулятор",
        "строить", "город", "мода", "одевалки", "макияж", "малыш", "питомец", "кошка", "собака",
        "лошадь", "динозавр", "дракон", "хоррор", "страшилки", "побег", "слова", "викторина",
        "математика", "раскраска", "рисовать", "гонки", "рыбалка", "без интернета", "для детей",
        "на двоих", "сортировка", "соедини", "кликер",
    ], suffixes=CYRILLIC),
    Market("tr", "tr", "Türkçe · Турция", [
        "oyun", "bulmaca", "araba", "motor", "kamyon", "otobüs", "park etme", "yemek", "restoran",
        "çiftlik", "zombi", "silah", "savaş", "futbol", "simülatör", "inşaat", "şehir", "moda",
        "giydirme", "makyaj", "bebek", "kedi", "köpek", "dinozor", "ejderha", "korku", "kaçış",
        "kelime", "bilgi yarışması", "matematik", "boyama", "çizim", "yarış", "balık tutma",
        "internetsiz", "çocuk", "2 kişilik", "birleştirme",
    ], suffixes=TURKISH),
    Market("ja", "jp", "日本語 · Япония", [
        "パズル", "ゲーム", "車", "バイク", "トラック", "バス", "駐車", "料理", "レストラン", "農場",
        "ゾンビ", "シューティング", "戦争", "サッカー", "シミュレーション", "街づくり", "着せ替え",
        "メイク", "赤ちゃん", "ペット", "猫", "犬", "恐竜", "ドラゴン", "ホラー", "脱出", "言葉",
        "クイズ", "計算", "塗り絵", "お絵かき", "レース", "釣り", "放置", "オフライン", "子供", "2人",
        "マージ", "仕分け",
    ], suffixes=KANA),
    Market("ko", "kr", "한국어 · Корея", [
        "퍼즐", "게임", "자동차", "오토바이", "트럭", "버스", "주차", "요리", "식당", "농장", "좀비",
        "슈팅", "전쟁", "축구", "시뮬레이션", "건설", "도시", "옷입히기", "메이크업", "아기", "펫",
        "고양이", "강아지", "공룡", "드래곤", "공포", "탈출", "단어", "퀴즈", "수학", "색칠", "그리기",
        "레이싱", "낚시", "방치형", "오프라인", "어린이", "2인용", "머지",
    ], suffixes=HANGUL),
]


def market(country: str) -> Market | None:
    return next((m for m in MARKETS if m.country == country), None)
