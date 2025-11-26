import discord
import os
import re
import random
import chess
import chess.engine
import chess.svg
import chess.pgn
import cairosvg
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
STOCKFISH_PATH = "stockfish/stockfish-windows-x86-64-avx2.exe"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# games[channel_id] = {
#     "board": ...,
#     "engine": ...,
#     "channel_id": ...,
#     "user_id": ...,
#     "color": None or "white" or "black",
#     "game_id": int,
#     "difficulty": None or int
# }
games = {}


def load_game_counter():
    os.makedirs("data", exist_ok=True)
    files = [f for f in os.listdir("data") if f.startswith("game_") and f.endswith(".pgn")]
    if not files:
        return 0
    numbers = []
    for name in files:
        try:
            n = int(name.split("_")[1].split(".")[0])
            numbers.append(n)
        except:
            pass
    return max(numbers) + 1


game_counter = load_game_counter()


def is_uci_move(txt):
    return bool(re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", txt))


def generate_image(user_id, board):
    os.makedirs(f"data/{user_id}", exist_ok=True)
    path = f"data/{user_id}/board.png"
    svg = chess.svg.board(board)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=path)
    return path


def save_pgn(game_id, board):
    pgn_path = f"data/game_{game_id}.pgn"
    game = chess.pgn.Game.from_board(board)
    with open(pgn_path, "w", encoding="utf8") as f:
        exporter = chess.pgn.FileExporter(f)
        game.accept(exporter)


USER_WIN_MESSAGES = [
    "The Rook cracks his knuckles and admits it quietly. You actually beat The Rook.",
    "The Rook squints at the board. That checkmate is real. Enjoy it, human.",
    "Muscles were not enough this time. Your tactics hit harder than The Rook expected.",
    "The Rook hates this result but respects the grind. Victory is yours.",
    "The Rook flexes, but the scoreboard still screams your win.",
    "The Rook logs this loss and promises revenge reps later. Nice finish.",
    "The Rook stares at the final position and mutters. That was clean.",
    "For once, The Rook is the one getting benched. Well played.",
    "The Rook will remember this defeat next time he loads the board.",
    "You outplayed The Rook. Say it fast before he changes his mind.",
    "The Rook thought this was a warm up. You turned it into a lesson.",
    "You just gave The Rook a tactical headache. Respect.",
    "The Rook flexes, but your checkmate flexed harder.",
    "The Rook lets out a slow exhale. You earned that final move.",
    "The Rook hates losing, but even he cannot argue with that board."
]

BOT_WIN_MESSAGES = [
    "The Rook does not blunder. Only humans do.",
    "The Rook wipes your king off the board and calls it leg day.",
    "You brought a pawn to an arm wrestle with The Rook.",
    "The Rook benches 300 and your Elo at the same time.",
    "Checkmate. The Rook barely had to warm up.",
    "Another fallen king. The Rook adds you to the collection.",
    "The Rook turns your position into a training exercise.",
    "The Rook calls this checkmate a light stretch.",
    "You just got rolled by pure concrete calculation.",
    "The Rook flexed once and your king collapsed.",
    "The Rook did not see resistance. Only extra cardio.",
    "The Rook stamps your king out like a warm up set.",
    "This game will live in The Rook highlight reel, not yours.",
    "The Rook saw mate while you were still staring at move one.",
    "The Rook nods. Another human folded exactly on schedule."
]

DRAW_MESSAGES = [
    "The Rook calls it a draw, but only because time is money.",
    "Balanced game. The Rook allows you to walk away.",
    "No winner, no loser. The Rook stays unimpressed.",
    "The Rook shrugs. Nobody got crushed, so it feels weird.",
    "A draw. The Rook calls it unfinished business.",
    "The Rook accepts this truce. For now.",
    "Stalemate. You did not lose, but you did not beat The Rook either.",
    "The Rook folds his arms. Fine. Call it equal.",
    "No knockout today. The Rook expected more chaos.",
    "Draw on the board, but The Rook insists he won spiritually.",
    "The Rook lets this one slide into the gray area.",
    "The Rook leans back. Not bad, not great, just chess.",
    "Nobody goes home with a crown this time.",
    "The Rook logs this as a neutral rep in his training.",
    "The board ran out of drama. The Rook moves on."
]


def rook_comment_from_delta(delta_cp: int) -> str:
    # delta_cp > 0  => ton coup améliore ta position
    # delta_cp < 0  => ton coup affaiblit ta position
    if delta_cp is None:
        return "The Rook tilts his head. That move is hard even for concrete muscles to rate."

    loss = -delta_cp if delta_cp < 0 else 0
    gain = delta_cp if delta_cp > 0 else 0

    if gain >= 120:
        return f"The Rook squints. That move pumps about {gain} points of raw value. Impressive."
    if gain >= 50:
        return f"The Rook nods. Solid move, you gained around {gain} points of position."
    if -40 <= delta_cp <= 40:
        return "The Rook shrugs. Decent move, nothing huge changed on the board."
    if loss >= 80 and loss < 200:
        return f"The Rook smirks. You just dropped roughly {loss} points of strength. Sloppy."
    if loss >= 200 and loss < 400:
        return f"The Rook laughs. That move leaks about {loss} points of muscle. Bad choice."
    if loss >= 400:
        return f"The Rook roars. You just threw away nearly {loss} points. That is a blunder carved in stone."
    # petite perte
    return "The Rook feels a small crack in your position. Not losing yet, but it smells."


async def create_new_game(user, guild):
    global game_counter

    hub = discord.utils.get(guild.text_channels, name="chess-hub")
    category = hub.category if hub else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True)
    }

    channel_name = f"chess-{game_counter}"
    channel = await guild.create_text_channel(
        channel_name,
        overwrites=overwrites,
        category=category
    )

    game_id = game_counter
    game_counter += 1

    board = chess.Board()
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

    games[channel.id] = {
        "board": board,
        "engine": engine,
        "channel_id": channel.id,
        "user_id": user.id,
        "color": None,
        "game_id": game_id,
        "difficulty": None
    }

    save_pgn(game_id, board)

    await channel.send(
        "Welcome to The Rook arena.\n\n"
        "Commands:\n"
        "♟ Play a move with UCI notation, example: e2e4\n"
        "🧠 Ask for analysis with: best move, analyse, best, idea, suggestion\n"
        "💀 Resign with: resign\n"
        "📷 The board image updates after every move.\n\n"
        "First, choose how strong The Rook should be."
    )

    await channel.send(view=DifficultyView())
    return channel


class RematchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Rematch?",
        style=discord.ButtonStyle.green,
        custom_id="rematch_button"
    )
    async def rematch(self, interaction, button):
        user = interaction.user
        guild = interaction.guild

        await interaction.response.send_message(
            "The Rook opens a fresh board for you.",
            ephemeral=True
        )

        channel = await create_new_game(user, guild)
        await interaction.followup.send(
            f"The Rook opens a new arena in {channel.mention}.",
            ephemeral=False
        )


class ColorChoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Play White",
        style=discord.ButtonStyle.blurple,
        custom_id="play_white_button"
    )
    async def white(self, interaction, button):
        channel_id = interaction.channel.id
        if channel_id not in games:
            await interaction.response.send_message(
                "The Rook sees no active game in this arena.",
                ephemeral=True
            )
            return

        game = games[channel_id]
        if interaction.user.id != game["user_id"]:
            await interaction.response.send_message(
                "The Rook is not playing this game with you.",
                ephemeral=True
            )
            return

        game["color"] = "white"

        board = game["board"]
        path = generate_image(game["user_id"], board)
        save_pgn(game["game_id"], board)

        await interaction.response.send_message(
            "You play White. The Rook waits for your first move.",
            ephemeral=True
        )
        await interaction.channel.send(file=discord.File(path))

    @discord.ui.button(
        label="Play Black",
        style=discord.ButtonStyle.grey,
        custom_id="play_black_button"
    )
    async def black(self, interaction, button):
        channel_id = interaction.channel.id
        if channel_id not in games:
            await interaction.response.send_message(
                "The Rook sees no active game in this arena.",
                ephemeral=True
            )
            return

        game = games[channel_id]
        if interaction.user.id != game["user_id"]:
            await interaction.response.send_message(
                "The Rook is not playing this game with you.",
                ephemeral=True
            )
            return

        game["color"] = "black"

        board = game["board"]
        engine = game["engine"]

        result = engine.play(board, chess.engine.Limit(depth=15))
        bot_move = result.move
        board.push(bot_move)
        path = generate_image(game["user_id"], board)
        save_pgn(game["game_id"], board)

        await interaction.response.send_message(
            "You play Black. The Rook takes the first punch.",
            ephemeral=True
        )
        await interaction.channel.send(f"My move: {bot_move.uci()}", file=discord.File(path))


class DifficultySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Beginner 1320 Elo", value="1320", description="The Rook lifts light today."),
            discord.SelectOption(label="Casual 1500 Elo", value="1500", description="The Rook warms up."),
            discord.SelectOption(label="Intermediate 1700 Elo", value="1700", description="The Rook starts to respect your presence."),
            discord.SelectOption(label="Advanced 1900 Elo", value="1900", description="The Rook focuses."),
            discord.SelectOption(label="Strong 2100 Elo", value="2100", description="The Rook flexes seriously."),
            discord.SelectOption(label="Expert 2300 Elo", value="2300", description="The Rook enjoys real competition."),
            discord.SelectOption(label="Master 2500 Elo", value="2500", description="The Rook trains for titles."),
            discord.SelectOption(label="Grandmaster 2700 Elo", value="2700", description="The Rook unleashes elite strength."),
            discord.SelectOption(label="The Rook Maximum 2850 Elo", value="2850", description="The Rook at full destructive power.")
        ]

        super().__init__(
            placeholder="Select The Rook difficulty",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="difficulty_select"
        )

    async def callback(self, interaction):
        channel_id = interaction.channel.id
        if channel_id not in games:
            await interaction.response.send_message(
                "The Rook sees no active game to configure here.",
                ephemeral=True
            )
            return

        game = games[channel_id]
        if interaction.user.id != game["user_id"]:
            await interaction.response.send_message(
                "Only The Rook opponent can set the difficulty.",
                ephemeral=True
            )
            return

        engine = game["engine"]

        elo = int(self.values[0])

        engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
        game["difficulty"] = elo

        await interaction.response.send_message(
            f"The Rook locks strength at {elo} Elo.",
            ephemeral=True
        )

        await interaction.channel.send(
            "Now choose your color.",
            view=ColorChoiceView()
        )


class DifficultyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DifficultySelect())


class StartGameButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Start Game",
        style=discord.ButtonStyle.green,
        custom_id="start_game_button"
    )
    async def start(self, interaction, button):
        user = interaction.user
        guild = interaction.guild

        channel = await create_new_game(user, guild)

        await interaction.response.send_message(
            f"The Rook opens a new arena in {channel.mention}.",
            ephemeral=False
        )


async def finalize_game(channel_id, channel, forced_winner=None):
    game = games.get(channel_id)
    if not game:
        return

    board = game["board"]
    engine = game["engine"]
    game_id = game["game_id"]

    try:
        engine.quit()
    except:
        pass

    save_pgn(game_id, board)

    winner_type = "draw"

    if forced_winner is not None:
        winner_type = forced_winner
    else:
        outcome = board.outcome()
        if outcome is not None:
            result = outcome.result()
            user_color = game["color"]
            if result == "1-0":
                winner_type = "user_win" if user_color == "white" else "bot_win"
            elif result == "0-1":
                winner_type = "user_win" if user_color == "black" else "bot_win"
            else:
                winner_type = "draw"

    if winner_type == "user_win":
        text = random.choice(USER_WIN_MESSAGES)
    elif winner_type == "bot_win":
        text = random.choice(BOT_WIN_MESSAGES)
    else:
        text = random.choice(DRAW_MESSAGES)

    await channel.send(text, view=RematchView())
    del games[channel_id]


@client.event
async def on_ready():
    print("Bot ready:", client.user)

    client.add_view(StartGameButton())
    client.add_view(DifficultyView())
    client.add_view(ColorChoiceView())
    client.add_view(RematchView())

    if not client.guilds:
        return

    guild = client.guilds[0]
    hub = discord.utils.get(guild.text_channels, name="chess-hub")
    if hub is None:
        return

    async for msg in hub.history(limit=50):
        if msg.author == client.user and "Press the button to start a game." in msg.content:
            return

    await hub.send("Press the button to start a game.", view=StartGameButton())


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    channel_id = message.channel.id
    txt = message.content.lower().strip()

    if channel_id not in games:
        return

    game = games[channel_id]

    if game["difficulty"] is None:
        await message.channel.send("Set The Rook difficulty first.")
        return

    if game["color"] is None:
        await message.channel.send("Choose your color first.")
        return

    board = game["board"]
    engine = game["engine"]
    user_id = game["user_id"]

    if message.author.id != user_id:
        await message.channel.send("The Rook only plays with the owner of this arena.")
        return

    if txt == "resign":
        await message.channel.send("The Rook accepts your resignation.")
        await finalize_game(channel_id, message.channel, forced_winner="bot_win")
        return

    if board.is_game_over():
        await message.channel.send("This game is already over. The Rook suggests a rematch.")
        return

    # move handling with commentary
    if is_uci_move(txt):
        # eval before move from user point of view
        user_color = chess.WHITE if game["color"] == "white" else chess.BLACK
        info_before = engine.analyse(board, chess.engine.Limit(depth=12))
        score_before_obj = info_before["score"].pov(user_color)
        cp_before = score_before_obj.score(mate_score=100000)

        try:
            board.push_uci(txt)
        except:
            await message.channel.send("Invalid move. The Rook expects legal chess.")
            return

        # eval after move
        info_after = engine.analyse(board, chess.engine.Limit(depth=12))
        score_after_obj = info_after["score"].pov(user_color)
        cp_after = score_after_obj.score(mate_score=100000)

        delta = None
        if cp_before is not None and cp_after is not None:
            delta = cp_after - cp_before

        comment = rook_comment_from_delta(delta)

        # image after your move
        path_user = generate_image(user_id, board)
        save_pgn(game["game_id"], board)

        await message.channel.send(
            file=discord.File(path_user)
        )
        await message.channel.send(comment)

        # if game is over after your move
        if board.is_game_over():
            await finalize_game(channel_id, message.channel)
            return

        # now The Rook plays
        result = engine.play(board, chess.engine.Limit(depth=15))
        bot_move = result.move
        board.push(bot_move)

        path_bot = generate_image(user_id, board)
        save_pgn(game["game_id"], board)

        await message.channel.send(
            f"My move: {bot_move.uci()}",
            file=discord.File(path_bot)
        )

        if board.is_game_over():
            await finalize_game(channel_id, message.channel)
        return

    if "meilleur" in txt or "analyse" in txt or "best" in txt:
        if board.is_game_over():
            await message.channel.send("The game is over. The Rook only analyses living positions.")
            return

        result = engine.analyse(board, chess.engine.Limit(depth=15))
        pv = result.get("pv")
        if pv:
            suggestion = pv[0].uci()
            await message.channel.send(f"The Rook suggests: {suggestion}")
        else:
            await message.channel.send("The Rook refuses to evaluate this.")
        return

    await message.channel.send("The Rook does not understand this command.")


client.run(TOKEN)
