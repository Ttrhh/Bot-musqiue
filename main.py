import os
import discord
import asyncio
from discord.ext import commands
import yt_dlp
from dotenv import load_dotenv

# Configuration
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Vérification des variables d'environnement
if not all([DISCORD_TOKEN, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET]):
    print("⚠️ Erreur: Variables d'environnement manquantes!")
    print("Assurez-vous d'avoir configuré DISCORD_TOKEN, SPOTIFY_CLIENT_ID et SPOTIFY_CLIENT_SECRET")
    exit(1)

# Spotify client setup
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
bot = commands.Bot(command_prefix="/", intents=intents)

# YT-DLP configuration
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,
    'socket_timeout': 15,
    'outtmpl': '%(title)s.%(ext)s',
    'restrictfilenames': True,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
        'Sec-Fetch-Mode': 'navigate',
    },
}

class MusicBot:
    def __init__(self):
        self.guilds = {}  # Stockage par serveur

    def get_guild_data(self, guild_id):
        if guild_id not in self.guilds:
            self.guilds[guild_id] = {
                'queue': [],
                'is_playing': False,
                'voice_client': None
            }
        return self.guilds[guild_id]

    async def play_next(self, ctx):
        guild_data = self.get_guild_data(ctx.guild.id)
        if len(guild_data['queue']) > 0:
            guild_data['is_playing'] = True
            url = guild_data['queue'].pop(0)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    url2 = info['url']
                    FFMPEG_OPTIONS = {
                        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                        'options': '-vn -b:a 128k'
                    }
                    source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)

                    # Créer le message "Now Playing"
                    embed = discord.Embed(
                        title="🎵 En cours de lecture",
                        description=f"**{info['title']}**",
                        color=discord.Color.blue()
                    )
                    embed.set_thumbnail(url=info.get('thumbnail'))
                    embed.add_field(name="Durée", value=f"{int(info['duration']/60)}:{int(info['duration']%60):02d}")

                    # Créer les boutons de contrôle
                    view = discord.ui.View()

                    skip_button = discord.ui.Button(style=discord.ButtonStyle.primary, emoji="⏭️", label="Skip")
                    async def skip_callback(interaction: discord.Interaction):
                        guild_data = music_bot.get_guild_data(interaction.guild_id)
                        if guild_data['voice_client']:
                            guild_data['voice_client'].stop()
                            await interaction.response.send_message("⏭️ Musique suivante...")
                    skip_button.callback = skip_callback

                    pause_button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="⏯️", label="Pause/Play")
                    async def pause_callback(interaction: discord.Interaction):
                        guild_data = music_bot.get_guild_data(interaction.guild_id)
                        if guild_data['voice_client']:
                            if guild_data['voice_client'].is_paused():
                                guild_data['voice_client'].resume()
                                await interaction.response.send_message("▶️ Musique reprise")
                            else:
                                guild_data['voice_client'].pause()
                                await interaction.response.send_message("⏸️ Musique en pause")
                    pause_button.callback = pause_callback

                    stop_button = discord.ui.Button(style=discord.ButtonStyle.danger, emoji="⏹️", label="Stop")
                    async def stop_callback(interaction: discord.Interaction):
                        guild_data = music_bot.get_guild_data(interaction.guild_id)
                        if guild_data['voice_client']:
                            guild_data['queue'].clear()
                            guild_data['voice_client'].stop()
                            await interaction.response.send_message("⏹️ Musique arrêtée")
                    stop_button.callback = stop_callback

                    view.add_item(pause_button)
                    view.add_item(skip_button)
                    view.add_item(stop_button)

                    # Envoyer le message
                    await ctx.channel.send(embed=embed, view=view)

                    guild_data['voice_client'].play(source, after=lambda e: bot.loop.create_task(self.play_next(ctx)))
            except Exception as e:
                print(f"Erreur lors de la lecture: {e}")
        else:
            guild_data['is_playing'] = False
            # Désactiver les boutons du dernier message
            async for message in ctx.channel.history(limit=50):
                if message.author == bot.user and len(message.components) > 0:
                    view = discord.ui.View()
                    for row in message.components:
                        for button in row.children:
                            new_button = discord.ui.Button(
                                style=button.style,
                                emoji=button.emoji,
                                label=button.label,
                                disabled=True
                            )
                            view.add_item(new_button)
                    await message.edit(view=view)
                    break

            if guild_data['voice_client']:
                await guild_data['voice_client'].disconnect()
                guild_data['voice_client'] = None

music_bot = MusicBot()

async def check_voice_channel():
    while True:
        await asyncio.sleep(30)  # Vérifier toutes les 30 secondes
        for guild in bot.guilds:
            guild_data = music_bot.get_guild_data(guild.id)
            if guild_data['voice_client'] is not None:
                members = guild_data['voice_client'].channel.members
                # Si personne n'est dans le salon vocal (sauf le bot)
                if len([m for m in members if not m.bot]) == 0:
                    await guild_data['voice_client'].disconnect()
                    guild_data['voice_client'] = None
                    guild_data['queue'] = []
                    guild_data['is_playing'] = False

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        # Démarrer la vérification du salon vocal
        bot.loop.create_task(check_voice_channel())
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="join", description="🎵 Rejoint ton salon vocal pour écouter de la musique")
async def join(interaction: discord.Interaction):
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        try:
            guild_data = music_bot.get_guild_data(interaction.guild_id)
            guild_data['voice_client'] = await channel.connect()
            embed = discord.Embed(
                title="🎵 Connexion réussie",
                description=f"Je suis connecté au salon **{channel}**",
                color=discord.Color.brand_green()
            )
            embed.add_field(name="👤 Demandé par", value=interaction.user.mention)
            embed.add_field(name="📡 Latence", value=f"{round(bot.latency * 1000)}ms")
            embed.set_footer(text="Utilisez /play pour lancer une musique !")
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Erreur de connexion",
                description=f"Une erreur est survenue : {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Salon vocal requis",
            description="Tu dois d'abord rejoindre un salon vocal !",
            color=discord.Color.red()
        )
        embed.set_footer(text="Rejoignez un salon vocal et réessayez")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="play", description="🎵 Joue une musique depuis YouTube ou Spotify")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    try:
        # Déterminer si c'est un lien Spotify ou YouTube
        is_spotify = 'spotify.com' in url.lower()

        if is_spotify:
            try:
                embed = discord.Embed(
                    title="⚠️ Support Spotify en Bêta",
                    description="Le support des liens Spotify est actuellement en bêta et peut ne pas fonctionner correctement. Veuillez utiliser un lien YouTube pour une meilleure expérience.",
                    color=discord.Color.yellow()
                )
                await interaction.followup.send(embed=embed)

                # Extraire l'ID de la piste Spotify
                if 'track' in url:
                    track_id = url.split('track/')[1].split('?')[0]
                else:
                    raise Exception("Le lien Spotify doit être celui d'une piste")

                try:
                    # Récupérer les informations de la piste Spotify
                    track_info = sp.track(track_id)
                    artist_name = track_info['artists'][0]['name']
                    track_name = track_info['name']

                    # Créer la requête de recherche YouTube
                    search_query = f"{artist_name} - {track_name} lyrics audio"

                    embed = discord.Embed(
                        title="🎵 Recherche en cours",
                        description=f"Recherche de **{track_name}** par **{artist_name}**",
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                except Exception as e:
                    raise Exception(f"Erreur lors de la récupération des informations Spotify: {str(e)}")

                # Rechercher sur YouTube
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    result = ydl.extract_info(f"ytsearch:{search_query}", download=False)
                    url = result['entries'][0]['webpage_url']
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Erreur Spotify",
                    description="Impossible de traiter le lien Spotify. Essayez avec un lien YouTube.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return

        # Vérifier d'abord la durée
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info['duration'] > 300:  # 300 secondes = 5 minutes
                embed = discord.Embed(
                    title="❌ Durée trop longue",
                    description="La musique dépasse 5 minutes !",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return

            # Si la durée est OK, on continue avec la connexion
            guild_data = music_bot.get_guild_data(interaction.guild_id)
            if not guild_data['voice_client']:
                if interaction.user.voice:
                    channel = interaction.user.voice.channel
                    guild_data['voice_client'] = await channel.connect()
                else:
                    embed = discord.Embed(
                        title="❌ Erreur",
                        description="Tu dois être dans un salon vocal !",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            embed = discord.Embed(
                title="🎵 Musique ajoutée",
                description=f"**{info['title']}** a été ajouté à la file d'attente",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=info.get('thumbnail'))
            embed.add_field(name="Durée", value=f"{int(info['duration']/60)}:{int(info['duration']%60):02d}")

            guild_data['queue'].append(url)
            await interaction.followup.send(embed=embed)

        if not guild_data['is_playing']:
            await music_bot.play_next(interaction)

    except Exception as e:
        try:
            error_embed = discord.Embed(
                title="❌ Erreur",
                description=f"Une erreur est survenue : {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed)
        except discord.errors.NotFound:
            pass

@bot.tree.command(name="skip", description="⏭️ Passe à la musique suivante dans la file d'attente")
async def skip(interaction: discord.Interaction):
    guild_data = music_bot.get_guild_data(interaction.guild_id)
    if guild_data['voice_client']:
        if guild_data['voice_client'].is_playing() or len(guild_data['queue']) > 0:
            if guild_data['voice_client'].is_playing():
                guild_data['voice_client'].stop()

            if len(guild_data['queue']) > 0:
                embed = discord.Embed(
                    title="⏭️ Musique suivante",
                    description="Passage à la musique suivante...",
                    color=discord.Color.blue()
                )
                embed.add_field(name="👤 Demandé par", value=interaction.user.mention)
                embed.add_field(name="📝 File d'attente", value=f"{len(music_bot.queue)} musique(s) restante(s)")
            else:
                embed = discord.Embed(
                    title="⏭️ Fin de la file d'attente",
                    description="Plus aucune musique à jouer",
                    color=discord.Color.blue()
                )
                embed.add_field(name="👤 Demandé par", value=interaction.user.mention)

            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Erreur",
                description="Aucune musique n'est en cours de lecture",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Non connecté",
            description="Je ne suis pas dans un salon vocal",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leave", description="👋 Quitte le salon vocal et vide la file d'attente")
async def leave(interaction: discord.Interaction):
    guild_data = music_bot.get_guild_data(interaction.guild_id)
    if guild_data['voice_client']:
        channel_name = guild_data['voice_client'].channel.name
        await guild_data['voice_client'].disconnect()
        guild_data['voice_client'] = None
        guild_data['queue'] = []
        guild_data['is_playing'] = False

        embed = discord.Embed(
            title="👋 Déconnexion",
            description=f"J'ai quitté le salon **{channel_name}**",
            color=discord.Color.brand_green()
        )
        embed.add_field(name="👤 Demandé par", value=interaction.user.mention)
        embed.add_field(name="🎵 File d'attente", value="Vidée")
        embed.set_footer(text="À bientôt !")
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Non connecté",
            description="Je ne suis pas dans un salon vocal",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

bot.run(DISCORD_TOKEN)
