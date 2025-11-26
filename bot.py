import discord
import os
import re
import chess
import chess.engine
import chess.svg
import cairosvg

import os

TOKEN = os.getenv('DISCORD_TOKEN')
STOCKFISH_PATH = "engine/stockfish/stockfish-windows-x86-64-avx2.exe"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

games = {}
game_counter = 0

def is_uci_move(txt):
    return bool(re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", txt))

def generate_image(user_id, board):
    os.makedirs(f"data/{user_id}", exist_ok=True)
    path = f"data/{user_id}/board.png"
    svg = chess.svg.board(board)
    cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=path)
    return path

class StartGameButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.green)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        global game_counter

        user = interaction.user
        guild = interaction.guild

        if user.id in games:
            await interaction.response.send_message(
                "You already have an ongoing game.", ephemeral=True
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True)
        }

        channel = await guild.create_text_channel(
            f"chess-{game_counter}",
            overwrites=overwrites
        )

        board = chess.Board()
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

        games[user.id] = {
            "board": board,
            "engine": engine,
            "channel_id": channel.id
        }

        game_counter += 1

        await interaction.response.send_message(
            f"Game created in {channel.mention}", ephemeral=True
        )
        await channel.send(f"{user.mention} game started. You play White. Send your first move in UCI format.")


@client.event
async def on_ready():
    print("Bot ready:", client.user)
    guild = discord.utils.get(client.guilds)

    for ch in guild.text_channels:
        if ch.name == "chess-hub":
            await ch.send("Press the button to start a game.", view=StartGameButton())
            break

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    user_id = message.author.id
    txt = message.content.lower().strip()

    if user_id not in games:
        return

    game = games[user_id]

    if message.channel.id != game["channel_id"]:
        return

    board = game["board"]
    engine = game["engine"]

    if is_uci_move(txt):
        try:
            board.push_uci(txt)
        except:
            await message.channel.send("Invalid move.")
            return

        result = engine.play(board, chess.engine.Limit(depth=15))
        bot_move = result.move
        board.push(bot_move)

        path = generate_image(user_id, board)

        await message.channel.send(f"My move: {bot_move.uci()}", file=discord.File(path))
        return

    if "meilleur" in txt or "analyse" in txt or "best" in txt:
        result = engine.analyse(board, chess.engine.Limit(depth=15))
        pv = result.get("pv")
        if pv:
            suggestion = pv[0].uci()
            await message.channel.send(f"Best move: {suggestion}")
        else:
            await message.channel.send("Cannot evaluate.")
        return

    await message.channel.send("Unknown command.")


client.run(TOKEN)
