# jogos_complexos.py
import discord
from discord.ext import commands
import random
import math
import asyncio
import datetime

# Importa nossas funções do DB
import database

# --- Constantes (copiadas do main.py) ---
NAIPES = ['❤️', '♦️', '♣️', '♠️']
VALORES_CARTAS = {
    'A': 11, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10
}


# --- 5. Classes de Lógica de Jogo (Blackjack, Crash, Duelo) ---

class Card:
    """Representa uma única carta de baralho."""
    def __init__(self, naipe, valor):
        self.naipe = naipe
        self.valor = valor # 'A', 'K', 'Q', 'J', '10', ...

    def __str__(self):
        return f"`{self.valor}{self.naipe}`"

class Deck:
    """Representa um baralho de 52 cartas."""
    def __init__(self):
        self.cartas = []
        self.build()
        self.shuffle()

    def build(self):
        for naipe in NAIPES:
            for valor in VALORES_CARTAS:
                self.cartas.append(Card(naipe, valor))

    def shuffle(self):
        random.shuffle(self.cartas)

    def deal(self):
        if len(self.cartas) > 0:
            return self.cartas.pop()
        return None # Fim do baralho

class BlackjackGame:
    """Guarda o estado de um jogo de Blackjack."""
    def __init__(self, bot, ctx, bet):
        self.bot = bot
        self.ctx = ctx
        self.bet = bet
        self.deck = Deck()
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
        self.message = None # A mensagem que será editada

    def calculate_score(self, hand):
        score = 0
        aces = 0
        for card in hand:
            score += VALORES_CARTAS[card.valor]
            if card.valor == 'A':
                aces += 1
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        return score

    def hand_to_string(self, hand, hide_first=False):
        if hide_first:
            return f"{hand[0]} `?`"
        return " ".join(str(card) for card in hand)

    async def start_game(self):
        """Inicia o jogo, distribui cartas e envia a primeira mensagem."""
        balance = database.get_balance(self.ctx.author.id)
        database.update_balance(self.ctx.author.id, balance['carteira'] - self.bet, balance['banco'])

        self.player_hand.append(self.deck.deal())
        self.dealer_hand.append(self.deck.deal())
        self.player_hand.append(self.deck.deal())
        self.dealer_hand.append(self.deck.deal())

        self.message = await self.ctx.send(embed=self.create_embed("Use `-hit` ou `-stand`"))

        player_score = self.calculate_score(self.player_hand)
        if player_score == 21:
            await self.end_game(True, "Blackjack! Você ganhou 1.5x a aposta!")

    def create_embed(self, footer_text):
        player_score = self.calculate_score(self.player_hand)
        dealer_score = self.calculate_score(self.dealer_hand)

        embed = discord.Embed(title=f"Blackjack (21) - Aposta: $ {self.bet:,}", color=discord.Color.dark_green())
        embed.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else discord.Embed.Empty)

        embed.add_field(name=f"Sua Mão ({player_score})", value=self.hand_to_string(self.player_hand), inline=False)
        embed.add_field(name=f"Mão do Dealer ({'?' if not self.game_over else dealer_score})", value=self.hand_to_string(self.dealer_hand, hide_first=not self.game_over), inline=False)
        embed.set_footer(text=footer_text)
        return embed

    async def player_hit(self):
        if self.game_over: return

        self.player_hand.append(self.deck.deal())
        player_score = self.calculate_score(self.player_hand)

        if player_score > 21:
            await self.end_game(False, "Estourou! Você perdeu.")
        elif player_score == 21:
            await self.player_stand()
        else:
            await self.message.edit(embed=self.create_embed("Use `-hit` ou `-stand`"))

    async def player_stand(self):
        if self.game_over: return
        self.game_over = True

        player_score = self.calculate_score(self.player_hand)
        dealer_score = self.calculate_score(self.dealer_hand)

        await self.message.edit(embed=self.create_embed("Dealer está jogando..."))
        await asyncio.sleep(1.5)

        while dealer_score < 17:
            self.dealer_hand.append(self.deck.deal())
            dealer_score = self.calculate_score(self.dealer_hand)
            await self.message.edit(embed=self.create_embed("Dealer está jogando..."))
            await asyncio.sleep(1)

        if dealer_score > 21:
            await self.end_game(True, "Dealer estourou! Você ganhou.")
        elif dealer_score > player_score:
            await self.end_game(False, "Dealer ganhou.")
        elif player_score > dealer_score:
            await self.end_game(True, "Você ganhou!")
        else:
            await self.end_game(False, "Empate! (Casa vence)", is_push=True)

    async def end_game(self, won, message="", is_push=False):
        self.game_over = True
        author_id = self.ctx.author.id

        taxa = float(database.get_config('taxa_casa'))
        balance = database.get_balance(author_id)

        log_msg = ""
        log_color = discord.Color.red()

        if won:
            player_score = self.calculate_score(self.player_hand)
            if player_score == 21 and len(self.player_hand) == 2:
                multiplicador = 2.5
                message = "Blackjack! Você ganhou 1.5x a aposta!"
            else:
                multiplicador = 2.0

            if self.bot.happy_hour:
                multiplicador *= self.bot.happy_hour_multiplier
                message += " (Bônus Happy Hour!)"

            multiplicador_real = multiplicador * (1 - taxa)
            ganhos = math.floor(self.bet * multiplicador_real)
            lucro = ganhos - self.bet
            nova_carteira = balance['carteira'] + ganhos

            await database.update_stats(author_id, vitorias_add=1)
            log_msg = f"**Blackjack (Vitória)**: {self.ctx.author.mention} apostou `$ {self.bet:,}` e lucrou `$ {lucro:,}`."
            log_color = discord.Color.green()

        elif is_push:
            nova_carteira = balance['carteira'] + self.bet
            log_msg = f"**Blackjack (Empate)**: {self.ctx.author.mention} apostou `$ {self.bet:,}` e recebeu a aposta de volta."
            log_color = discord.Color.greyple()

        else:
            nova_carteira = balance['carteira']
            await database.update_stats(author_id, derrotas_add=1)
            log_msg = f"**Blackjack (Derrota)**: {self.ctx.author.mention} apostou e perdeu `$ {self.bet:,}`."

        database.update_balance(author_id, nova_carteira, balance['banco'])

        await self.message.edit(embed=self.create_embed(f"FIM DE JOGO: {message}"))
        await self.bot.log_action(log_msg, log_color)
        await database.db_log(author_id, "BLACKJACK", f"Aposta: {self.bet}, Resultado: {message}")

        del self.bot.active_blackjack_games[author_id]

class CrashGame:
    """Guarda o estado de um jogo de Crash (para todos)."""
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.cashed_out = {}
        self.multiplier = 1.00
        self.game_task = None
        self.message = None
        self.lock = asyncio.Lock()
        self.stage = "waiting"

    async def add_player(self, ctx, bet):
        if self.stage != "waiting":
            await ctx.send("O jogo de Crash já começou. Espere o próximo!")
            return False

        if ctx.author.id in self.players:
            await ctx.send("Você já está nesta rodada do Crash.")
            return False

        async with self.lock:
            self.players[ctx.author.id] = bet
            balance = database.get_balance(ctx.author.id)
            database.update_balance(ctx.author.id, balance['carteira'] - bet, balance['banco'])

            await ctx.send(f"{ctx.author.mention} entrou no Crash com **$ {bet:,}**!")
            await self.bot.log_action(f"**Crash (Entrou)**: {ctx.author.mention} apostou `$ {bet:,}`.", discord.Color.blue())
            await database.db_log(ctx.author.id, "CRASH_ENTRADA", f"Aposta: {bet}")

        return True

    def create_embed(self):
        if self.stage == "waiting":
            color = discord.Color.greyple()
            desc = "Jogo de Crash vai começar em **10 segundos**!\nDigite `-crash <valor>` para entrar."
        elif self.stage == "running":
            color = discord.Color.gold()
            desc = f"Multiplicador: **{self.multiplier:.2f}x**\nDigite `-sacarcrash` para sair!"
        else:
            color = discord.Color.red()
            desc = f"💥 **CRASH!** 💥\nO foguete explodiu em **{self.multiplier:.2f}x**!"

        embed = discord.Embed(title="🚀 Jogo do Crash 🚀", description=desc, color=color)

        player_list_str = "Ninguém"
        if self.players:
            player_list = []
            for uid, bet in self.players.items():
                user = self.bot.get_user(uid)
                if user:
                    player_list.append(f"{user.display_name}: $ {bet:,}")
            if player_list:
                player_list_str = "\n".join(player_list)
        embed.add_field(name="Jogando Agora", value=player_list_str, inline=True)

        cashed_list_str = "Ninguém"
        if self.cashed_out:
            cashed_list = []
            for uid, multi in self.cashed_out.items():
                user = self.bot.get_user(uid)
                if user:
                    cashed_list.append(f"{user.display_name}: {multi:.2f}x")
            if cashed_list:
                cashed_list_str = "\n".join(cashed_list)
        embed.add_field(name="Saíram com Lucro", value=cashed_list_str, inline=True)

        return embed

    async def start_game(self, channel):
        self.message = await channel.send(embed=self.create_embed())
        await asyncio.sleep(10)

        async with self.lock:
            if not self.players:
                self.stage = "crashed"
                await self.message.edit(embed=self.create_embed(), content="Ninguém entrou no Crash. Jogo cancelado.")
                self.bot.current_crash_game = None
                return

            self.stage = "running"
            await self.message.edit(embed=self.create_embed())

        self.game_task = self.bot.loop.create_task(self.run_game_loop())

    async def run_game_loop(self):
        try:
            crash_point = (1 / max(0.01, random.expovariate(1.0))) * 2.0 + 1.01

            while self.multiplier < crash_point:
                sleep_time = max(0.05, 0.5 / (self.multiplier * 0.5 + 1))
                await asyncio.sleep(sleep_time)

                async with self.lock:
                    self.multiplier += 0.01 + (self.multiplier * 0.02)
                    if self.message:
                        await self.message.edit(embed=self.create_embed())

            await self.end_game()

        except asyncio.CancelledError:
            print("Loop do Crash cancelado.")
            self.stage = "crashed"
            if self.message:
                await self.message.edit(content="Jogo de Crash cancelado.", embed=None)
            self.bot.current_crash_game = None
        except Exception as e:
            print(f"Erro no loop do Crash: {e}")
            self.bot.current_crash_game = None

    async def player_cash_out(self, user):
        if self.stage != "running":
            await user.send("Você só pode sacar enquanto o jogo está rodando.")
            return

        async with self.lock:
            if user.id not in self.players:
                return

            bet = self.players.pop(user.id)
            self.cashed_out[user.id] = self.multiplier

            taxa = float(database.get_config('taxa_casa'))
            multiplicador_real = self.multiplier

            if self.bot.happy_hour:
                multiplicador_real *= self.bot.happy_hour_multiplier

            ganhos = math.floor((bet * multiplicador_real) * (1 - taxa))
            lucro = ganhos - bet

            balance = database.get_balance(user.id)
            database.update_balance(user.id, balance['carteira'] + ganhos, balance['banco'])

            await database.update_stats(user.id, vitorias_add=1)
            log_msg = f"**Crash (Saída)**: {user.mention} sacou em {self.multiplier:.2f}x e lucrou `$ {lucro:,}`."
            if self.bot.happy_hour:
                log_msg += " (HH)"

            await self.bot.log_action(log_msg, discord.Color.green())
            await database.db_log(user.id, "CRASH_SAIDA", f"Aposta: {bet}, Multi: {self.multiplier:.2f}, Lucro: {lucro}")

            await user.send(f"Você sacou **$ {ganhos:,}** (lucro de $ {lucro:,}) com **{self.multiplier:.2f}x**!")

            if self.message:
                await self.message.edit(embed=self.create_embed())

    async def end_game(self):
        async with self.lock:
            if self.stage == "crashed": return
            self.stage = "crashed"

            if self.message:
                await self.message.edit(embed=self.create_embed())

            if not self.players:
                if self.message:
                    await self.message.channel.send("Todos saíram a tempo! Ninguém perdeu.")
            else:
                perdedores_msg = ""
                for user_id, bet in self.players.items():
                    user = self.bot.get_user(user_id)
                    if user:
                        perdedores_msg += f"{user.mention} "

                    await database.update_stats(user_id, derrotas_add=1)
                    await self.bot.log_action(f"**Crash (Derrota)**: {user.mention if user else f'ID {user_id}'} perdeu `$ {bet:,}`.", discord.Color.red())
                    await database.db_log(user_id, "CRASH_DERROTA", f"Aposta: {bet}, Multi: {self.multiplier:.2f}")

                if self.message:
                    await self.message.channel.send(f"{perdedores_msg} não saíram a tempo e perderam suas apostas!")

            self.bot.current_crash_game = None

class Duelo:
    """Guarda o estado de um desafio de duelo."""
    def __init__(self, author, target, bet):
        self.author = author
        self.target = target
        self.bet = bet
        self.created_at = datetime.datetime.now()


# --- Classe Principal do Cog ---

class JogosComplexos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot # Armazena a instância do bot principal

    # --- Comandos de Blackjack ---
    @commands.command(name='blackjack', aliases=['bj'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def blackjack(self, ctx, *, valor: str):
        """Inicia um jogo de Blackjack (21)."""
        author_id = ctx.author.id
        if author_id in self.bot.active_blackjack_games:
            return await ctx.send("Você já tem um jogo de Blackjack em andamento.")
        if self.bot.current_crash_game and author_id in self.bot.current_crash_game.players:
            return await ctx.send("Você não pode jogar Blackjack enquanto está no Crash!")

        # Usamos a função de verificação que está DENTRO do bot
        aposta_valida, amount = await self.bot.verificar_e_processar_aposta(ctx, ctx.author, valor)
        if not aposta_valida: return

        game = BlackjackGame(self.bot, ctx, amount)
        self.bot.active_blackjack_games[author_id] = game
        await game.start_game()

    @commands.command(name='hit')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def hit(self, ctx):
        """Pede mais uma carta no Blackjack."""
        game = self.bot.active_blackjack_games.get(ctx.author.id)
        if not game:
            return await ctx.send("Você não está em um jogo de Blackjack.")
        await game.player_hit()

    @commands.command(name='stand')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def stand(self, ctx):
        """Para de pedir cartas no Blackjack."""
        game = self.bot.active_blackjack_games.get(ctx.author.id)
        if not game:
            return await ctx.send("Você não está em um jogo de Blackjack.")
        await game.player_stand()

    # --- Comandos do Crash ---
    @commands.command(name='crash')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def crash(self, ctx, *, valor: str):
        """Entra no próximo jogo de Crash."""
        author_id = ctx.author.id
        if author_id in self.bot.active_blackjack_games:
            return await ctx.send("Você não pode entrar no Crash enquanto joga Blackjack!")

        aposta_valida, amount = await self.bot.verificar_e_processar_aposta(ctx, ctx.author, valor)
        if not aposta_valida: return

        if self.bot.current_crash_game is None:
            self.bot.current_crash_game = CrashGame(self.bot)
            await self.bot.current_crash_game.add_player(ctx, amount)
            await self.bot.current_crash_game.start_game(ctx.channel)
        else:
            await self.bot.current_crash_game.add_player(ctx, amount)

    @commands.command(name='sacarcrash')
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def sacarcrash(self, ctx):
        """Sai do jogo de Crash com o multiplicador atual."""
        game = self.bot.current_crash_game
        if not game:
            return await ctx.send("Não há nenhum jogo de Crash rodando.", delete_after=5)

        await game.player_cash_out(ctx.author)
        try:
            await ctx.message.delete()
        except discord.errors.NotFound:
            pass

    # --- Comandos de Duelo ---
    @commands.command(name='duelo')
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def duelo(self, ctx, target: discord.Member, *, valor: str):
        """Desafia outro jogador para um duelo de sorte (dado 1-100)."""
        author = ctx.author
        if author.id == target.id:
            return await ctx.send("Você não pode duelar consigo mesmo.")
        if target.bot:
            return await ctx.send("Você não pode duelar com um bot.")
        if target.id in self.bot.active_duelos:
            return await ctx.send(f"{target.display_name} já tem um desafio pendente.")

        aposta_valida, amount = await self.bot.verificar_e_processar_aposta(ctx, ctx.author, valor)
        if not aposta_valida: return

        await database.check_user(target.id)
        target_balance = database.get_balance(target.id)
        if target_balance['carteira'] < amount:
            return await ctx.send(f"{target.display_name} não tem **$ {amount:,}** na carteira para aceitar este duelo.")

        novo_duelo = Duelo(author, target, amount)
        self.bot.active_duelos[target.id] = novo_duelo

        await ctx.send(
            f"⚔️ **DESAFIO!** ⚔️\n{target.mention}, {author.mention} te desafiou para um duelo valendo **$ {amount:,}**!\n"
            f"Você tem 60 segundos para digitar `-aceitar` ou `-recusar`."
        )

        await asyncio.sleep(60)
        if target.id in self.bot.active_duelos:
            del self.bot.active_duelos[target.id]
            await ctx.send(f"O desafio de {author.mention} para {target.mention} expirou.")

    @commands.command(name='aceitar')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def aceitar(self, ctx):
        """Aceita um desafio de duelo."""
        author_id = ctx.author.id
        duelo = self.bot.active_duelos.get(author_id)

        if not duelo:
            return await ctx.send("Você não tem nenhum desafio pendente.")

        del self.bot.active_duelos[author_id]

        author = duelo.author
        target = duelo.target
        bet = duelo.bet

        author_balance = database.get_balance(author.id)
        target_balance = database.get_balance(target.id)

        if author_balance['carteira'] < bet:
            return await ctx.send(f"{author.mention} não tem mais o dinheiro para o duelo.")
        if target_balance['carteira'] < bet:
            return await ctx.send(f"Você não tem mais o dinheiro para o duelo.")

        database.update_balance(author.id, author_balance['carteira'] - bet, author_balance['banco'])
        database.update_balance(target.id, target_balance['carteira'] - bet, target_balance['banco'])

        author_roll = random.randint(1, 100)
        target_roll = random.randint(1, 100)

        embed = discord.Embed(title=f"⚔️ Duelo: {author.display_name} vs {target.display_name}", color=discord.Color.dark_red())
        embed.add_field(name=f"{author.display_name} rolou:", value=f"**{author_roll}**", inline=True)
        embed.add_field(name=f"{target.display_name} rolou:", value=f"**{target_roll}**", inline=True)

        while author_roll == target_roll:
            embed.add_field(name="EMPATE!", value="Rolando novamente...", inline=False)
            author_roll = random.randint(1, 100)
            target_roll = random.randint(1, 100)
            embed.add_field(name=f"{author.display_name} (novo):", value=f"**{author_roll}**", inline=True)
            embed.add_field(name=f"{target.display_name} (novo):", value=f"**{target_roll}**", inline=True)

        if author_roll > target_roll:
            ganhador = author
            perdedor = target
        else:
            ganhador = target
            perdedor = author

        taxa = float(database.get_config('taxa_casa'))
        premio = math.floor((bet * 2) * (1 - taxa))
        lucro = premio - bet

        ganhador_balance = database.get_balance(ganhador.id)
        database.update_balance(ganhador.id, ganhador_balance['carteira'] + premio, ganhador_balance['banco'])

        embed.description = f"**{ganhador.mention} venceu** e ganhou **$ {premio:,}** (Lucro: $ {lucro:,})!"
        await ctx.send(embed=embed)

        await database.update_stats(ganhador.id, vitorias_add=1)
        await database.update_stats(perdedor.id, derrotas_add=1)

        log_msg = f"**Duelo (Vitória)**: {ganhador.mention} venceu {perdedor.mention} e lucrou `$ {lucro:,}` (Aposta: `$ {bet:,}`)."
        await self.bot.log_action(log_msg, discord.Color.green())
        await database.db_log(ganhador.id, "DUELO_VITORIA", f"Aposta: {bet}, Vs: {perdedor.id}, Roll: {author_roll}v{target_roll}")
        await database.db_log(perdedor.id, "DUELO_DERROTA", f"Aposta: {bet}, Vs: {ganhador.id}, Roll: {author_roll}v{target_roll}")

    @commands.command(name='recusar')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def recusar(self, ctx):
        """Recusa um desafio de duelo."""
        duelo = self.bot.active_duelos.get(ctx.author.id)

        if not duelo:
            return await ctx.send("Você não tem nenhum desafio pendente.")

        del self.bot.active_duelos[ctx.author.id]
        await ctx.send(f"Você recusou o desafio de {duelo.author.mention}.")


# --- Função de Setup (Obrigatória) ---
async def setup(bot):
    await bot.add_cog(JogosComplexos(bot))
    print("[jogos_complexos.py] Cog de Jogos Complexos carregado.")
