# main.py
import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import re
import datetime
import random
import math
import asyncio
import traceback
from datetime import timezone, timedelta 
import sqlite3 

# Importa o nosso novo arquivo de banco de dados
import database

# --- 1. Configuração Inicial ---
print("Carregando variáveis de ambiente...")
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ROLE_ID = os.getenv("ADMIN_ROLE_ID")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

if not all([TOKEN, ADMIN_ROLE_ID, LOG_CHANNEL_ID]):
    print("ERRO CRÍTICO: Uma ou mais variáveis no .env não foram definidas!")
    exit()

try:
    ADMIN_ROLE_ID = int(ADMIN_ROLE_ID)
    LOG_CHANNEL_ID = int(LOG_CHANNEL_ID)
except ValueError:
    print("ERRO CRÍTICO: ADMIN_ROLE_ID ou LOG_CHANNEL_ID no .env não são números válidos.")
    exit()

# --- 2. Constantes de Jogo (Apenas as simples) ---
BASE_RECOMPENSA_DAILY = 250
BONUS_STREAK_DAILY = 50
BRT = timezone(timedelta(hours=-3)) # Fuso horário de Brasília (UTC-3)

SLOT_EMOJIS = [
    ("🍒", 10, 3.0), ("🍋", 10, 3.0), ("🍉", 8,  5.0),
    ("⭐", 5,  10.0), ("💎", 3,  25.0), ("💰", 1,  0)
]

CORES_ROLETA = {
    'vermelho': {'multi': 2, 'numeros': [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]},
    'preto':    {'multi': 2, 'numeros': [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]},
    'verde':    {'multi': 14, 'numeros': [0]}
}

# --- 6. Definição da Classe do Bot ---
print("Configurando a classe do Bot...")

class CassinoBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.admin_role_id = ADMIN_ROLE_ID
        self.log_channel_id = LOG_CHANNEL_ID

        # Gerenciadores de Estado de Jogo (O Cog vai acessá-los)
        self.active_blackjack_games = {}
        self.active_duelos = {}
        self.current_crash_game = None

        # Funcionalidades Automáticas
        self.happy_hour = False
        self.happy_hour_multiplier = 1.3

    async def setup_hook(self):
        """Função que roda para iniciar tasks e carregar Cogs."""
        self.happy_hour_task.start()
        print("Task de Happy Hour iniciada.")

        # Carrega o nosso novo arquivo de Cog
        try:
            await self.load_extension('jogos_complexos')
        except Exception as e:
            print(f"ERRO CRÍTICO ao carregar 'jogos_complexos.py': {e}")
            traceback.print_exc()

    # Task para a "Happy Hour"
    @tasks.loop(hours=1)
    async def happy_hour_task(self):
        try:
            if not self.happy_hour and random.random() < 0.2:
                self.happy_hour = True
                await self.log_action("🎉 **HAPPY HOUR INICIADA!** 🎉\nTodos os ganhos em jogos terão **+30%** pela próxima hora!", discord.Color.gold())
                await asyncio.sleep(3600) 
                self.happy_hour = False
                await self.log_action("A Happy Hour terminou.", discord.Color.greyple())
        except Exception as e:
            print(f"Erro na task de Happy Hour: {e}")

    @happy_hour_task.before_loop
    async def before_happy_hour_task(self):
        await self.wait_until_ready()
        print("Bot pronto, iniciando loop de Happy Hour.")

    # --- 4. Funções Auxiliares (AGORA DENTRO DO BOT) ---

    async def log_action(self, message: str, color=discord.Color.greyple()):
        """Envia uma mensagem de log para o canal definido no bot."""
        try:
            channel = self.get_channel(self.log_channel_id)
            if channel:
                embed = discord.Embed(description=message, color=color, timestamp=datetime.datetime.now())
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Erro ao tentar enviar log do canal: {e}")

    def parse_amount(self, amount_str: str, max_val: int = None) -> int | str:
        """Converte a entrada de <valor> (ex: "100k", "5b", "all") em um número inteiro."""
        amount_str = str(amount_str).lower().strip()
        if amount_str == 'all':
            return max_val if max_val is not None else "Não é possível usar 'all' neste comando."
        cleaned_str = re.sub(r'[,\.$ ]', '', amount_str)
        multiplier = 1
        if cleaned_str.endswith('k'): multiplier = 1_000; cleaned_str = cleaned_str[:-1]
        elif cleaned_str.endswith('m'): multiplier = 1_000_000; cleaned_str = cleaned_str[:-1]
        elif cleaned_str.endswith('b'): multiplier = 1_000_000_000; cleaned_str = cleaned_str[:-1]
        try:
            value = int(float(cleaned_str) * multiplier)
            if value <= 0: return "O valor deve ser positivo."
            return value
        except ValueError:
            return "Valor inválido. Use números (ex: 1000), '1k', '1.5m', etc."

    def is_admin(self):
        """Check para comandos de admin."""
        async def predicate(ctx):
            admin_role = ctx.guild.get_role(self.admin_role_id)
            if admin_role is None:
                await ctx.send(f"Erro de configuração: O cargo de Admin (ID: {self.admin_role_id}) não foi encontrado.")
                return False
            if admin_role not in ctx.author.roles:
                await ctx.send("Você não tem permissão para usar este comando.")
                return False
            return True
        return commands.check(predicate)

    async def verificar_e_processar_aposta(self, ctx, autor, valor_str):
        """Função auxiliar para validar uma aposta."""
        await database.check_user(autor.id) # Usa a função do database.py
        balance = database.get_balance(autor.id)
        max_aposta = int(database.get_config('max_aposta'))

        amount = self.parse_amount(valor_str, max_val=balance['carteira'])

        if isinstance(amount, str):
            await ctx.send(amount)
            return (False, None)

        if amount > balance['carteira']:
            await ctx.send("Você não tem todo esse dinheiro na carteira para apostar.")
            return (False, None)

        if amount > max_aposta:
            await ctx.send(f"Sua aposta excede a aposta máxima permitida de **$ {max_aposta:,}**.")
            return (False, None)

        return (True, amount)


# --- 7. Instância do Bot ---
print("Criando instância do Bot...")
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = CassinoBot(command_prefix='-', intents=intents, help_command=None)


# --- 8. Eventos Principais do Bot ---
print("Configurando eventos do Bot...")

@bot.event
async def on_ready():
    """Disparado quando o bot conecta."""
    print(f'Bot conectado como {bot.user}')
    print(f'Prefixo: {bot.command_prefix}')
    database.init_db() # Chama a função do database.py
    await bot.change_presence(activity=discord.Game(name="-ajuda | Faça sua aposta!"))

@bot.event
async def on_command_error(ctx, error):
    """Gerenciador de erros global."""
    if isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Está faltando um argumento. Ex: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.CheckFailure):
        pass
    elif isinstance(error, commands.MemberNotFound):
         await ctx.send(f"Membro não encontrado. Você precisa @mencionar o usuário.")
    elif isinstance(error, commands.CommandOnCooldown):
        tempo_restante = error.retry_after
        await ctx.send(f"Calma! Você pode usar este comando novamente em **{tempo_restante:.1f} segundos**.", delete_after=5)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Argumento inválido. Verifique o `-ajuda` para ver como usar o comando.")
    elif isinstance(error, (commands.CommandInvokeError, commands.HybridCommandError)):
        # Erro dentro do comando
        original_error = error.original
        print(f"Erro inesperado no comando {ctx.command}: {original_error}")
        await ctx.send("Ocorreu um erro inesperado ao processar seu comando.")
        traceback.print_exception(type(original_error), original_error, original_error.__traceback__)
    else:
        # Outros erros
        print(f"Erro não tratado: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)


# --- 9. Comandos de Economia ---
print("Configurando comandos de Economia...")

@bot.command(name='saldo', aliases=['bal', 'dinheiro', 'carteira'])
async def saldo(ctx, member: discord.Member = None):
    target_user = member or ctx.author
    await database.check_user(target_user.id)
    balance = database.get_balance(target_user.id)
    if balance:
        total = balance['carteira'] + balance['banco']
        embed = discord.Embed(title=f"💰 Saldo de {target_user.display_name}", color=discord.Color.gold())
        embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else discord.Embed.Empty)
        embed.add_field(name="Carteira", value=f"$ {balance['carteira']:,}", inline=True)
        embed.add_field(name="Banco", value=f"$ {balance['banco']:,}", inline=True)
        embed.add_field(name="Total", value=f"$ {total:,}", inline=False)
        embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
        await ctx.send(embed=embed)

@bot.command(name='banco')
async def banco(ctx):
    await saldo(ctx, member=None)

@bot.command(name='depositar', aliases=['dep'])
@commands.cooldown(1, 3, commands.BucketType.user)
async def depositar(ctx, *, valor: str):
    author_id = ctx.author.id
    await database.check_user(author_id)
    balance = database.get_balance(author_id)
    amount = bot.parse_amount(valor, max_val=balance['carteira'])
    if isinstance(amount, str): return await ctx.send(amount)
    if amount > balance['carteira']: return await ctx.send("Você não tem esse dinheiro na carteira.")

    new_carteira = balance['carteira'] - amount
    new_banco = balance['banco'] + amount
    database.update_balance(author_id, new_carteira, new_banco)

    embed = discord.Embed(title="🏦 Depósito Realizado", description=f"Você depositou **$ {amount:,}** no banco.", color=discord.Color.green())
    embed.add_field(name="Nova Carteira", value=f"$ {new_carteira:,}", inline=True)
    embed.add_field(name="Novo Saldo no Banco", value=f"$ {new_banco:,}", inline=True)
    await ctx.send(embed=embed)
    await bot.log_action(f"**Depósito**: {ctx.author.mention} depositou `$ {amount:,}`.", discord.Color.green())
    await database.db_log(author_id, "DEPOSITO", f"Valor: {amount}")

@bot.command(name='sacar', aliases=['withdraw'])
@commands.cooldown(1, 3, commands.BucketType.user)
async def sacar(ctx, *, valor: str):
    author_id = ctx.author.id
    await database.check_user(author_id)
    balance = database.get_balance(author_id)
    amount = bot.parse_amount(valor, max_val=balance['banco'])
    if isinstance(amount, str): return await ctx.send(amount)
    if amount > balance['banco']: return await ctx.send("Você não tem esse dinheiro no banco.")

    new_carteira = balance['carteira'] + amount
    new_banco = balance['banco'] - amount
    database.update_balance(author_id, new_carteira, new_banco)

    embed = discord.Embed(title="💸 Saque Realizado", description=f"Você sacou **$ {amount:,}** do banco.", color=discord.Color.orange())
    embed.add_field(name="Nova Carteira", value=f"$ {new_carteira:,}", inline=True)
    embed.add_field(name="Novo Saldo no Banco", value=f"$ {new_banco:,}", inline=True)
    await ctx.send(embed=embed)
    await bot.log_action(f"**Saque**: {ctx.author.mention} sacou `$ {amount:,}`.", discord.Color.orange())
    await database.db_log(author_id, "SAQUE", f"Valor: {amount}")

@bot.command(name='pagar', aliases=['pay'])
@commands.cooldown(1, 10, commands.BucketType.user)
async def pagar(ctx, member: discord.Member, *, valor: str):
    author = ctx.author
    target = member
    if author.id == target.id: return await ctx.send("Você não pode pagar a si mesmo.")
    if target.bot: return await ctx.send("Você não pode pagar um bot.")

    await database.check_user(author.id)
    await database.check_user(target.id)
    author_balance = database.get_balance(author.id)
    amount = bot.parse_amount(valor, max_val=author_balance['carteira'])
    if isinstance(amount, str): return await ctx.send(amount)
    if amount > author_balance['carteira']: return await ctx.send("Você não tem dinheiro suficiente na carteira.")

    target_balance = database.get_balance(target.id)
    new_author_carteira = author_balance['carteira'] - amount
    new_target_carteira = target_balance['carteira'] + amount

    database.update_balance(author.id, new_author_carteira, author_balance['banco'])
    database.update_balance(target.id, new_target_carteira, target_balance['banco'])

    embed = discord.Embed(title="💸 Pagamento Realizado", description=f"Você pagou **$ {amount:,}** para {target.mention}.", color=discord.Color.blue())
    embed.set_footer(text=f"{author.display_name} -> {target.display_name}")
    await ctx.send(embed=embed)
    await bot.log_action(f"**Pagamento**: {author.mention} pagou `$ {amount:,}` para {target.mention}.", discord.Color.blue())
    await database.db_log(author.id, "PAGAMENTO", f"Valor: {amount}, Para: {target.id}")

@bot.command(name='daily')
@commands.cooldown(1, 10, commands.BucketType.user)
async def daily(ctx):
    """Coleta sua recompensa diária (reseta às 00:00 de Brasília)."""
    author_id = ctx.author.id
    await database.check_user(author_id)

    conn = sqlite3.connect(database.DB_NAME) 
    cursor = conn.cursor()
    cursor.execute("SELECT last_daily, daily_streak, carteira, banco FROM usuarios WHERE user_id = ?", (author_id,))
    data = cursor.fetchone()
    last_daily_str, streak, carteira, banco = data

    try:
        last_daily_time_naive = datetime.datetime.fromisoformat(last_daily_str)
        if last_daily_time_naive.tzinfo is None:
            last_daily_time_naive = last_daily_time_naive.replace(tzinfo=timezone.utc)
    except ValueError:
        last_daily_time_naive = datetime.datetime(2000, 1, 1, tzinfo=timezone.utc)

    now_brt = datetime.datetime.now(BRT)
    last_daily_brt = last_daily_time_naive.astimezone(BRT)

    today_brt = now_brt.date()
    last_daily_date_brt = last_daily_brt.date()

    if today_brt == last_daily_date_brt:
        amanha_brt = (now_brt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        tempo_restante = amanha_brt - now_brt

        horas, rem = divmod(tempo_restante.seconds, 3600)
        minutos, _ = divmod(rem, 60)
        await ctx.send(f"Você já coletou seu daily hoje! Tente novamente em **{horas}h {minutos}m** (às 00:00 no horário de Brasília).")
        conn.close()
        return

    ontem_brt = today_brt - timedelta(days=1)
    if last_daily_date_brt == ontem_brt:
        streak += 1
    else:
        streak = 1

    recompensa_total = BASE_RECOMPENSA_DAILY + (streak * BONUS_STREAK_DAILY)
    nova_carteira = carteira + recompensa_total

    now_utc_iso = datetime.datetime.now(timezone.utc).isoformat()

    cursor.execute("UPDATE usuarios SET carteira = ?, daily_streak = ?, last_daily = ? WHERE user_id = ?", (nova_carteira, streak, now_utc_iso, author_id))
    conn.commit()
    conn.close()

    embed = discord.Embed(title="🌟 Recompensa Diária", description=f"Você coletou sua recompensa diária de **$ {recompensa_total:,}**!", color=discord.Color.brand_green())
    embed.add_field(name="Novo Saldo (Carteira)", value=f"$ {nova_carteira:,}", inline=True)
    embed.add_field(name="Streak Atual", value=f"🔥 {streak} dias", inline=True)
    embed.set_footer(text="Volte amanhã (00:00 de Brasília) para mais!")
    await ctx.send(embed=embed)

    await bot.log_action(f"**Daily**: {ctx.author.mention} coletou `$ {recompensa_total:,}` (Streak: {streak} dias).", discord.Color.brand_green())
    await database.db_log(author_id, "DAILY", f"Valor: {recompensa_total}, Streak: {streak}")


# --- 10. Comandos de Jogos de Cassino (Simples) ---
print("Configurando comandos de Jogos Simples...")

@bot.command(name='coin', aliases=['cf', 'flip'])
@commands.cooldown(1, 5, commands.BucketType.user)
async def coin(ctx, lado: str, *, valor: str):
    lado_escolhido = lado.lower()
    if lado_escolhido not in ['cara', 'coroa']:
        return await ctx.send("Escolha inválida. Você deve escolher `cara` ou `coroa`.")

    aposta_valida, amount = await bot.verificar_e_processar_aposta(ctx, ctx.author, valor)
    if not aposta_valida: return

    author_id = ctx.author.id
    balance = database.get_balance(author_id)
    taxa = float(database.get_config('taxa_casa'))
    multiplicador = 2.0

    if bot.happy_hour:
        multiplicador *= bot.happy_hour_multiplier

    resultado = random.choice(['cara', 'coroa'])

    embed = discord.Embed(title="🪙 Cara ou Coroa", description=f"Você apostou **$ {amount:,}** em **{lado_escolhido.capitalize()}**.\nA moeda está girando...", color=discord.Color.light_grey())
    msg = await ctx.send(embed=embed)
    await asyncio.sleep(1.5) 

    lucro = 0
    if lado_escolhido == resultado:
        multiplicador_real = multiplicador * (1 - taxa)
        ganhos = math.floor(amount * multiplicador_real)
        lucro = ganhos - amount
        nova_carteira = balance['carteira'] + ganhos

        embed.description = f"Deu **{resultado.capitalize()}**! Você ganhou **$ {ganhos:,}** (Lucro: $ {lucro:,})!"
        if bot.happy_hour:
             embed.description += " (Bônus Happy Hour!)"
        embed.color = discord.Color.green()

        await database.update_stats(author_id, vitorias_add=1)
        log_msg = f"**Coinflip (Vitória)**: {ctx.author.mention} apostou `$ {amount:,}` e lucrou `$ {lucro:,}`."
        log_color = discord.Color.green()
    else:
        nova_carteira = balance['carteira'] - amount
        lucro = -amount
        embed.description = f"Deu **{resultado.capitalize()}**... Você perdeu **$ {amount:,}**."
        embed.color = discord.Color.red()

        await database.update_stats(author_id, derrotas_add=1)
        log_msg = f"**Coinflip (Derrota)**: {ctx.author.mention} apostou e perdeu `$ {amount:,}`."
        log_color = discord.Color.red()

    database.update_balance(author_id, nova_carteira, balance['banco'])
    embed.add_field(name="Nova Carteira", value=f"$ {nova_carteira:,}")
    await msg.edit(embed=embed)
    await bot.log_action(log_msg, log_color)
    await database.db_log(author_id, "COINFLIP", f"Aposta: {amount}, Lucro: {lucro}, Resultado: {resultado}")

@bot.command(name='dice', aliases=['dado'])
@commands.cooldown(1, 5, commands.BucketType.user)
async def dice(ctx, numero_escolhido: int, *, valor: str):
    if not (1 <= numero_escolhido <= 99):
        return await ctx.send("Número inválido. Você deve escolher um número entre **1** e **99**.")

    aposta_valida, amount = await bot.verificar_e_processar_aposta(ctx, ctx.author, valor)
    if not aposta_valida: return

    author_id = ctx.author.id
    balance = database.get_balance(author_id)
    taxa = float(database.get_config('taxa_casa'))

    chance_vitoria = (100 - numero_escolhido) / 100.0
    multiplicador = (1 / chance_vitoria)

    if bot.happy_hour:
        multiplicador *= bot.happy_hour_multiplier

    multiplicador_real = multiplicador * (1 - taxa)
    dado = random.randint(1, 100)

    embed = discord.Embed(title="🎲 Jogo do Dado", description=f"Você apostou **$ {amount:,}** que o dado cairia **acima de {numero_escolhido}**.", color=discord.Color.dark_orange())
    embed.add_field(name="Seu Número", value=f"> {numero_escolhido}", inline=True)
    embed.add_field(name="Multiplicador", value=f"{multiplicador_real:.2f}x", inline=True)
    msg = await ctx.send(embed=embed)
    await asyncio.sleep(1.5)

    embed.add_field(name="Resultado do Dado", value=f"**{dado}**", inline=False)

    lucro = 0
    if dado > numero_escolhido:
        ganhos = math.floor(amount * multiplicador_real)
        lucro = ganhos - amount
        nova_carteira = balance['carteira'] + ganhos
        embed.description = f"O dado caiu em **{dado}**! Você ganhou **$ {ganhos:,}** (Lucro: $ {lucro:,})!"
        if bot.happy_hour:
             embed.description += " (Bônus Happy Hour!)"
        embed.color = discord.Color.green()

        await database.update_stats(author_id, vitorias_add=1)
        log_msg = f"**Dice (Vitória)**: {ctx.author.mention} apostou `$ {amount:,}` (> {numero_escolhido}) e lucrou `$ {lucro:,}`."
        log_color = discord.Color.green()
    else:
        nova_carteira = balance['carteira'] - amount
        lucro = -amount
        embed.description = f"O dado caiu em **{dado}**... Você perdeu **$ {amount:,}**."
        embed.color = discord.Color.red()

        await database.update_stats(author_id, derrotas_add=1)
        log_msg = f"**Dice (Derrota)**: {ctx.author.mention} apostou `$ {amount:,}` (> {numero_escolhido}) e perdeu."
        log_color = discord.Color.red()

    database.update_balance(author_id, nova_carteira, balance['banco'])
    embed.add_field(name="Nova Carteira", value=f"$ {nova_carteira:,}", inline=False)
    await msg.edit(embed=embed)
    await bot.log_action(log_msg, log_color)
    await database.db_log(author_id, "DICE", f"Aposta: {amount}, Acima de: {numero_escolhido}, Lucro: {lucro}, Resultado: {dado}")

@bot.command(name='roleta', aliases=['roulette'])
@commands.cooldown(1, 7, commands.BucketType.user)
async def roleta(ctx, cor: str, *, valor: str):
    cor_escolhida = cor.lower()
    if cor_escolhida not in CORES_ROLETA:
        return await ctx.send("Cor inválida. Escolha `vermelho`, `preto` ou `verde`.")

    aposta_valida, amount = await bot.verificar_e_processar_aposta(ctx, ctx.author, valor)
    if not aposta_valida: return

    author_id = ctx.author.id
    balance = database.get_balance(author_id)
    taxa = float(database.get_config('taxa_casa'))

    numero_sorteado = random.randint(0, 36)
    cor_sorteada = ""

    if numero_sorteado in CORES_ROLETA['vermelho']['numeros']: cor_sorteada = 'vermelho'
    elif numero_sorteado in CORES_ROLETA['preto']['numeros']: cor_sorteada = 'preto'
    elif numero_sorteado in CORES_ROLETA['verde']['numeros']: cor_sorteada = 'verde'

    emoji_cor = {'vermelho': '🟥', 'preto': '⬛', 'verde': '🟩'}.get(cor_sorteada)

    embed = discord.Embed(title="🎰 Roleta", description=f"Você apostou **$ {amount:,}** no **{cor_escolhida.capitalize()}**.\nA roleta está girando...", color=discord.Color.dark_purple())
    msg = await ctx.send(embed=embed)
    await asyncio.sleep(2.0)

    lucro = 0
    if cor_escolhida == cor_sorteada:
        multiplicador = CORES_ROLETA[cor_sorteada]['multi']
        if bot.happy_hour:
            multiplicador *= bot.happy_hour_multiplier

        multiplicador_real = multiplicador * (1 - taxa)
        ganhos = math.floor(amount * multiplicador_real)
        lucro = ganhos - amount
        nova_carteira = balance['carteira'] + ganhos

        embed.description = f"A bola caiu no **{numero_sorteado} {emoji_cor} {cor_sorteada.capitalize()}**!\nVocê ganhou **$ {ganhos:,}** (Lucro: $ {lucro:,})!"
        if bot.happy_hour:
             embed.description += " (Bônus Happy Hour!)"
        embed.color = discord.Color.green()

        await database.update_stats(author_id, vitorias_add=1)
        log_msg = f"**Roleta (Vitória)**: {ctx.author.mention} apostou `$ {amount:,}` no {cor_escolhida} e lucrou `$ {lucro:,}`."
        log_color = discord.Color.green()
    else:
        nova_carteira = balance['carteira'] - amount
        lucro = -amount
        embed.description = f"A bola caiu no **{numero_sorteado} {emoji_cor} {cor_sorteada.capitalize()}**...\nVocê perdeu **$ {amount:,}**."
        embed.color = discord.Color.red()

        await database.update_stats(author_id, derrotas_add=1)
        log_msg = f"**Roleta (Derrota)**: {ctx.author.mention} apostou `$ {amount:,}` no {cor_escolhida} e perdeu."
        log_color = discord.Color.red()

    database.update_balance(author_id, nova_carteira, balance['banco'])
    embed.add_field(name="Nova Carteira", value=f"$ {nova_carteira:,}")
    await msg.edit(embed=embed)
    await bot.log_action(log_msg, log_color)
    await database.db_log(author_id, "ROLETA", f"Aposta: {amount}, Cor: {cor_escolhida}, Lucro: {lucro}, Resultado: {numero_sorteado} {cor_sorteada}")

@bot.command(name='slots')
@commands.cooldown(1, 5, commands.BucketType.user)
async def slots(ctx, *, valor: str):
    aposta_valida, amount = await bot.verificar_e_processar_aposta(ctx, ctx.author, valor)
    if not aposta_valida: return

    author_id = ctx.author.id
    balance = database.get_balance(author_id)
    taxa = float(database.get_config('taxa_casa'))
    taxa_jackpot = float(database.get_config('taxa_jackpot'))
    jackpot_atual = int(database.get_config('jackpot'))

    contribuicao_jackpot = math.floor(amount * taxa_jackpot)
    novo_jackpot = jackpot_atual + contribuicao_jackpot
    database.update_config('jackpot', str(novo_jackpot))

    emojis = [e[0] for e in SLOT_EMOJIS]
    pesos = [e[1] for e in SLOT_EMOJIS]
    colunas = random.choices(emojis, weights=pesos, k=3) 

    embed = discord.Embed(title="🎰 Caça-Níquel", description=f"Você apostou **$ {amount:,}**.\nGirando...", color=discord.Color.dark_gold())
    embed.add_field(name="Jackpot Atual", value=f"💰 $ {novo_jackpot:,}")
    embed.add_field(name="Resultado", value=f"```\n[ ? | ? | ? ]\n```", inline=False)
    msg = await ctx.send(embed=embed)
    await asyncio.sleep(1.5)

    resultado_str = f"```\n[ {colunas[0]} | {colunas[1]} | {colunas[2]} ]\n```"
    embed.set_field_at(1, name="Resultado", value=resultado_str, inline=False)

    lucro = 0
    if colunas[0] == colunas[1] == colunas[2]:
        simbolo_ganhador = colunas[0]
        if simbolo_ganhador == "💰":
            ganhos = jackpot_atual
            lucro = ganhos
            nova_carteira = balance['carteira'] + ganhos

            embed.description = f"🌟 **J A C K P O T** 🌟\nVocê ganhou o jackpot de **$ {ganhos:,}**!"
            embed.color = discord.Color.gold()
            database.update_config('jackpot', '100000')
            await database.update_stats(author_id, vitorias_add=1)
            log_msg = f"**SLOTS (JACKPOT!)**: {ctx.author.mention} apostou `$ {amount:,}` e ganhou o jackpot de `$ {ganhos:,}`!"
            log_color = discord.Color.gold()
        else:
            multiplicador = 0
            for e in SLOT_EMOJIS:
                if e[0] == simbolo_ganhador: multiplicador = e[2]; break

            if bot.happy_hour:
                multiplicador *= bot.happy_hour_multiplier

            multiplicador_real = multiplicador * (1 - taxa)
            ganhos = math.floor(amount * multiplicador_real)
            lucro = ganhos - amount
            nova_carteira = balance['carteira'] + ganhos

            embed.description = f"**Três iguais!** {simbolo_ganhador} {simbolo_ganhador} {simbolo_ganhador}\nVocê ganhou **$ {ganhos:,}** (Lucro: $ {lucro:,})!"
            if bot.happy_hour:
                 embed.description += " (Bônus Happy Hour!)"
            embed.color = discord.Color.green()
            await database.update_stats(author_id, vitorias_add=1)
            log_msg = f"**Slots (Vitória)**: {ctx.author.mention} apostou `$ {amount:,}` e lucrou `$ {lucro:,}`."
            log_color = discord.Color.green()

    elif colunas[0] == colunas[1] or colunas[1] == colunas[2] or colunas[0] == colunas[2]:
        ganhos = math.floor(amount * 0.5)
        lucro = ganhos - amount
        nova_carteira = balance['carteira'] + ganhos
        embed.description = f"**Dois iguais!** Você recebe metade da aposta de volta. Perdeu **$ {-lucro:,}**."
        embed.color = discord.Color.light_grey()
        await database.update_stats(author_id, derrotas_add=1)
        log_msg = f"**Slots (Parcial)**: {ctx.author.mention} apostou `$ {amount:,}` e perdeu `$ {-lucro:,}`."
        log_color = discord.Color.greyple()

    else:
        nova_carteira = balance['carteira'] - amount
        lucro = -amount
        embed.description = f"**Sem sorte!** Você perdeu **$ {amount:,}**."
        embed.color = discord.Color.red()
        await database.update_stats(author_id, derrotas_add=1)
        log_msg = f"**Slots (Derrota)**: {ctx.author.mention} apostou e perdeu `$ {amount:,}`."
        log_color = discord.Color.red()

    database.update_balance(author_id, nova_carteira, balance['banco'])
    embed.add_field(name="Nova Carteira", value=f"$ {nova_carteira:,}", inline=False)
    await msg.edit(embed=embed)
    await bot.log_action(log_msg, log_color)
    await database.db_log(author_id, "SLOTS", f"Aposta: {amount}, Lucro: {lucro}, Resultado: {' '.join(colunas)}")

# --- (Comandos de Jogos Complexos movidos para jogos_complexos.py) ---

# --- 11. Comandos de Extras e Diversão ---
print("Configurando comandos Extras...")

@bot.command(name='sorte')
async def sorte(ctx):
    semente = str(ctx.author.id) + str(datetime.date.today())
    seeded_random = random.Random(semente)
    sorte_num = seeded_random.randint(1, 10)

    if sorte_num == 1: msg = "Hoje não é seu dia... (1/10)"
    elif sorte_num <= 3: msg = "Melhor ter cuidado... (3/10)"
    elif sorte_num <= 6: msg = "Um dia comum. (6/10)"
    elif sorte_num <= 9: msg = "Estou me sentindo com sorte! (9/10)"
    else: msg = "É O SEU DIA DE SORTE! (10/10)"
    await ctx.send(f"🍀 A sua sorte hoje é: **{msg}**")

@bot.command(name='perfil', aliases=['profile'])
@commands.cooldown(1, 5, commands.BucketType.user)
async def perfil(ctx, member: discord.Member = None):
    target_user = member or ctx.author
    if target_user.bot: return

    await database.check_user(target_user.id)

    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT carteira, banco, daily_streak FROM usuarios WHERE user_id = ?", (target_user.id,))
    user_data = cursor.fetchone()
    cursor.execute("SELECT vitorias, derrotas FROM stats WHERE user_id = ?", (target_user.id,))
    stats_data = cursor.fetchone()
    conn.close()

    if not user_data or not stats_data:
        return await ctx.send("Não foi possível carregar o perfil deste usuário.")

    carteira, banco, streak = user_data
    vitorias, derrotas = stats_data
    total = carteira + banco

    if vitorias == 0 and derrotas == 0: wl_ratio = "N/A"
    elif derrotas == 0: wl_ratio = f"{vitorias:.1f}"
    else: wl_ratio = f"{(vitorias / derrotas):.1f}"

    embed = discord.Embed(title=f"👤 Perfil de {target_user.display_name}", color=discord.Color.dark_teal())
    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else discord.Embed.Empty)
    embed.add_field(name="💰 Saldo Total", value=f"**$ {total:,}**", inline=False)
    embed.add_field(name="Carteira", value=f"$ {carteira:,}", inline=True)
    embed.add_field(name="Banco", value=f"$ {banco:,}", inline=True)
    embed.add_field(name="📊 Estatísticas", value=f"Vitórias: **{vitorias}**\nDerrotas: **{derrotas}**\nW/L Ratio: **{wl_ratio}**", inline=False)
    embed.add_field(name="🔥 Streak (Daily)", value=f"**{streak}** dias", inline=True)
    await ctx.send(embed=embed)

@bot.command(name='rank', aliases=['top', 'leaderboard'])
@commands.cooldown(1, 15, commands.BucketType.guild)
async def rank(ctx):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, (carteira + banco) as total_money FROM usuarios ORDER BY total_money DESC LIMIT 10")
    top_users = cursor.fetchall()
    conn.close()

    embed = discord.Embed(title="🏆 Ranking dos Mais Ricos 🏆", description="Top 10 jogadores com mais dinheiro (carteira + banco).", color=discord.Color.gold())

    if not top_users:
        embed.description = "Ainda não há ninguém no ranking."
        return await ctx.send(embed=embed)

    rank_string = ""
    rank_count = 1
    for user_id, total_money in top_users:
        member = ctx.guild.get_member(user_id)
        if member:
            rank_string += f"**{rank_count}.** {member.display_name} - **$ {total_money:,}**\n"
            rank_count += 1

    if not rank_string:
        embed.description = "Nenhum jogador do ranking está neste servidor."

    embed.add_field(name="Placar", value=rank_string)
    await ctx.send(embed=embed)

# --- 12. Comandos de Administração ---
print("Configurando comandos de Admin...")

@bot.command(name='addmoney')
@bot.is_admin() 
async def addmoney(ctx, member: discord.Member, *, valor: str):
    if member.bot: return
    target_id = member.id
    await database.check_user(target_id)
    balance = database.get_balance(target_id)
    amount = bot.parse_amount(valor)
    if isinstance(amount, str): return await ctx.send(amount)

    new_carteira = balance['carteira'] + amount
    database.update_balance(target_id, new_carteira, balance['banco'])

    embed = discord.Embed(title="💸 Dinheiro Adicionado (Admin)", description=f"**$ {amount:,}** foram adicionados à carteira de {member.mention}.", color=discord.Color.blurple())
    embed.add_field(name="Novo Saldo (Carteira)", value=f"$ {new_carteira:,}")
    await ctx.send(embed=embed)
    await bot.log_action(f"**Admin (add)**: {ctx.author.mention} adicionou `$ {amount:,}` para {member.mention}.", discord.Color.red())
    await database.db_log(ctx.author.id, "ADDMONEY", f"Valor: {amount}, Para: {target_id}")

@bot.command(name='removemoney')
@bot.is_admin()
async def removemoney(ctx, member: discord.Member, *, valor: str):
    if member.bot: return
    target_id = member.id
    await database.check_user(target_id)
    balance = database.get_balance(target_id)
    amount = bot.parse_amount(valor, max_val=balance['carteira']) 
    if isinstance(amount, str): return await ctx.send(amount)

    nova_carteira = max(0, balance['carteira'] - amount)
    valor_removido = balance['carteira'] - nova_carteira 

    database.update_balance(target_id, nova_carteira, balance['banco'])

    embed = discord.Embed(title="🚫 Dinheiro Removido (Admin)", description=f"**$ {valor_removido:,}** foram removidos da carteira de {member.mention}.", color=discord.Color.dark_red())
    embed.add_field(name="Novo Saldo (Carteira)", value=f"$ {nova_carteira:,}")
    await ctx.send(embed=embed)
    await bot.log_action(f"**Admin (rem)**: {ctx.author.mention} removeu `$ {valor_removido:,}` de {member.mention}.", discord.Color.red())
    await database.db_log(ctx.author.id, "REMOVEMONEY", f"Valor: {valor_removido}, De: {target_id}")

@bot.command(name='settaxa')
@bot.is_admin()
async def settaxa(ctx, porcentagem: float):
    if not (0 <= porcentagem <= 100):
        return await ctx.send("A taxa deve ser uma porcentagem entre 0 e 100.")

    valor_db = porcentagem / 100.0
    database.update_config('taxa_casa', str(valor_db))
    await ctx.send(f"✅ A taxa da casa foi definida para **{porcentagem}%**.\n(Jogadores receberão {100-porcentagem}% do prêmio justo).")
    await bot.log_action(f"**Admin (config)**: {ctx.author.mention} alterou a taxa da casa para `{porcentagem}%`.", discord.Color.red())

@bot.command(name='setmax')
@bot.is_admin()
async def setmax(ctx, *, valor: str):
    amount = bot.parse_amount(valor)
    if isinstance(amount, str): return await ctx.send(amount)

    database.update_config('max_aposta', str(amount))
    await ctx.send(f"✅ A aposta máxima foi definida para **$ {amount:,}**.")
    await bot.log_action(f"**Admin (config)**: {ctx.author.mention} alterou a aposta máxima para `$ {amount:,}`.", discord.Color.red())

@bot.command(name='logs')
@bot.is_admin()
async def logs(ctx, limit: int = 15):
    if not (1 <= limit <= 50):
        return await ctx.send("O limite deve ser entre 1 e 50.")

    logs_data = await database.get_db_logs(limit)
    if not logs_data:
        return await ctx.send("Nenhum log encontrado no banco de dados.")

    embed = discord.Embed(title=f"Últimos {len(logs_data)} Logs do Banco de Dados", color=discord.Color.dark_grey())
    desc = ""
    for log in logs_data:
        timestamp, user_id, action, details = log
        data_formatada = datetime.datetime.fromisoformat(timestamp).strftime("%d/%m %H:%M")
        user = bot.get_user(user_id)
        user_mention = user.mention if user else f"ID: {user_id}"
        desc += f"`[{data_formatada}]` **{action}** - {user_mention} - *{details}*\n"

    if len(desc) > 4096:
        desc = desc[:4090] + "\n... (logs omitidos)"

    embed.description = desc
    await ctx.send(embed=embed)

@bot.command(name='resetar')
@bot.is_admin()
async def resetar(ctx):
    embed = discord.Embed(
        title="⚠️ ATENÇÃO - RESETE DE ECONOMIA ⚠️",
        description="Você está prestes a apagar **TODOS** os saldos, bancos, streaks e estatísticas de **TODOS** os jogadores.\n"
                    "Isso não pode ser desfeito.\n\n"
                    "Digite `EU CONFIRMO O RESETE DA ECONOMIA` para continuar.",
        color=discord.Color.red()
    )
    msg = await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content == "EU CONFIRMO O RESETE DA ECONOMIA"

    try:
        await bot.wait_for('message', check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await msg.edit(content="Tempo esgotado. Resete cancelado.", embed=None)
    else:
        await msg.edit(content="**RESETANDO ECONOMIA...**", embed=None)
        await database.reset_economy()
        await msg.edit(content="✅ **ECONOMIA RESETADA COM SUCESSO!**")
        await bot.log_action(f"🔥🔥 **ECONOMIA GLOBAL RESETADA** por {ctx.author.mention} 🔥🔥", discord.Color.red())
        await database.db_log(ctx.author.id, "RESET_GLOBAL", "Economia resetada.")

# --- 13. Comandos de Outros ---
print("Configurando comandos Finais...")

@bot.command(name='ping')
async def ping(ctx):
    latency_ms = bot.latency * 1000 
    embed = discord.Embed(title="Pong! 🏓", description=f"Minha latência é de **{latency_ms:.2f} ms**.", color=discord.Color.green())
    await ctx.send(embed=embed)

# --- COMANDO 'SOBRE' MODIFICADO ---
@bot.command(name='sobre', aliases=['info'])
async def sobre(ctx):
    """Mostra informações sobre o projeto."""
    embed = discord.Embed(title="🎰 Bot de Cassino 🎰", description="Um bot de cassino focado em economia e apostas, criado em Python.", color=discord.Color.blue())

    # --- CRÉDITOS ALTERADOS ---
    embed.add_field(name="👑 Criador", value="**Ninhoous**")

    embed.add_field(name="Versão", value="3.2.0 (White-label)")
    embed.add_field(name="Biblioteca", value=f"discord.py {discord.__version__}")
    embed.set_footer(text="Aposte com responsabilidade!")
    await ctx.send(embed=embed)

@bot.command(name='ajuda', aliases=['help', 'comandos'])
async def ajuda(ctx):
    prefixo = bot.command_prefix 

    embed = discord.Embed(title="🎰 Central de Ajuda do Cassino 🎰", description=f"Use o prefixo `{prefixo}` antes de cada comando.", color=discord.Color.blue())

    embed.add_field(
        name="💵 ECONOMIA",
        value=f"`{prefixo}saldo [@usuario]` - Mostra seu saldo.\n"
              f"`{prefixo}banco` - Mostra seu saldo.\n"
              f"`{prefixo}depositar <valor/all>` - Deposita dinheiro no banco.\n"
              f"`{prefixo}sacar <valor/all>` - Saca dinheiro do banco.\n"
              f"`{prefixo}pagar <@usuario> <valor>` - Envia dinheiro para outro jogador.\n"
              f"`{prefixo}daily` - Coleta sua recompensa diária.\n",
        inline=False
    )

    embed.add_field(
        name="🎮 JOGOS DE CASSINO",
        value=f"`{prefixo}coin <cara/coroa> <valor>` - Joga cara ou coroa.\n"
              f"`{prefixo}dice <1-99> <valor>` - Aposta acima de um número no dado (1-100).\n"
              f"`{prefixo}roleta <cor> <valor>` - Aposta no vermelho, preto ou verde.\n"
              f"`{prefixo}slots <valor>` - Gira o caça-níquel (chance de Jackpot!).\n"
              f"`{prefixo}blackjack <valor>` - Inicia um jogo de Blackjack (21).\n"
              f"`{prefixo}hit` - Pede mais uma carta no Blackjack.\n"
              f"`{prefixo}stand` - Para de pedir cartas no Blackjack.\n"
              f"`{prefixo}crash <valor>` - Entra no jogo de Crash.\n"
              f"`{prefixo}sacarcrash` - Sai do Crash com o lucro atual.\n"
              f"`{prefixo}duelo <@usuario> <valor>` - Desafia outro jogador para um duelo.\n"
              f"`{prefixo}aceitar` - Aceita um duelo pendente.\n"
              f"`{prefixo}recusar` - Recusa um duelo pendente.\n",
        inline=False
    )

    embed.add_field(
        name="🧠 EXTRAS E DIVERSÃO",
        value=f"`{prefixo}perfil [@usuario]` - Mostra o perfil de estatísticas.\n"
              f"`{prefixo}rank` / `{prefixo}top` - Mostra os 10 mais ricos.\n"
              f"`{prefixo}sorte` - Mostra sua sorte do dia.\n",
        inline=False
    )

    embed.add_field(
        name="⚙️ ADMINISTRAÇÃO",
        value=f"`{prefixo}addmoney <@usuario> <valor>` - Adiciona dinheiro a um membro.\n"
              f"`{prefixo}removemoney <@usuario> <valor>` - Remove dinheiro de um membro.\n"
              f"`{prefixo}settaxa <porcentagem>` - Define a taxa da casa (ex: 5 para 5%).\n"
              f"`{prefixo}setmax <valor>` - Define a aposta máxima nos jogos.\n"
              f"`{prefixo}logs [limite]` - Mostra os últimos logs do banco de dados.\n"
              f"`{prefixo}resetar` - Reseta TODA a economia (requer confirmação).\n",
        inline=False
    )

    embed.add_field(
        name="🧩 OUTROS",
        value=f"`{prefixo}ajuda` - Mostra esta mensagem.\n"
              f"`{prefixo}ping` - Verifica a latência do bot.\n"
              f"`{prefixo}sobre` - Informações do bot.\n",
        inline=False
    )

    embed.set_footer(text="Divirta-se e aposte com responsabilidade!")
    await ctx.send(embed=embed)


# --- 14. Roda o Bot ---
if __name__ == "__main__":
    print("Iniciando o bot...")
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("="*50)
        print("ERRO CRÍTICO: TOKEN INVÁLIDO.")
        print("="*50)
    except Exception as e:
        print(f"Um erro ocorreu ao tentar iniciar o bot: {e}")
