# Cassino

# 🎰 Bot de Cassino Premium para Discord

Um bot de cassino completo e profissional escrito em Python, focado em economia persistente, jogos clássicos e apostas interativas. Perfeito para engajar comunidades e criar um sistema de economia divertido e competitivo.

Este bot é **plug-and-play**: configure e comece a usar em minutos.

---

## ✨ Funcionalidades Principais

Este bot foi projetado para ser um cassino puro, com todos os recursos que você esperaria de um servidor de apostas de alta qualidade.

### 💵 Economia Completa e Persistente
Os dados dos jogadores **são salvos!** O bot usa um banco de dados **SQLite** local, o que significa que se o bot reiniciar, o dinheiro, as vitórias e as streaks de todos estarão seguros.

* `-saldo`: Mostra o dinheiro na carteira e no banco.
* `-banco`: Alias para `-saldo`.
* `-depositar <valor/all>`: Guarda seu dinheiro com segurança no banco.
* `-sacar <valor/all>`: Tira o dinheiro do banco para a carteira.
* `-pagar <@usuário> <valor>`: Transfere dinheiro para outro jogador.
* `-daily`: Coleta uma recompensa diária com sistema de **streak automático**.

### 🎮 Jogos de Cassino (Clássicos)
Jogos rápidos e divertidos para apostas imediatas.

* `-slots <valor>`: Gira o caça-níquel. Inclui sistema de **Jackpot Acumulativo**!
* `-roleta <cor> <valor>`: Aposte em `vermelho`, `preto` ou `verde` (verde paga 14x).
* `-coin <lado> <valor>`: Um simples e rápido cara ou coroa.
* `-dice <1-99> <valor>`: Aposte que o dado (1-100) cairá **acima** do número escolhido.

### 🚀 Jogos Interativos (Avançados)
Jogos complexos que mantêm os jogadores engajados.

* **Blackjack (21):**
    * `-blackjack <valor>`: Começa um jogo contra o dealer (bot).
    * `-hit`: Pede mais uma carta.
    * `-stand`: Para e espera a vez do dealer.
* **Crash (Foguetinho):**
    * `-crash <valor>`: Entra na próxima rodada do jogo do foguetinho.
    * `-sacarcrash`: Sai do jogo no multiplicador atual para garantir seus lucros antes que ele "crashe".
* **Duelo de Sorte:**
    * `-duelo <@usuário> <valor>`: Desafia outro jogador para um duelo de sorte valendo dinheiro.
    * `-aceitar` / `-recusar`: Responde a um desafio.

### 🧠 Extras e Competição
Recursos sociais para engajar a comunidade.

* `-perfil [@usuário]`: Mostra um perfil detalhado com saldo total, vitórias, derrotas e streak do daily.
* `-rank` / `-top`: Mostra o Top 10 jogadores mais ricos do servidor.
* `-sorte`: Mostra a sorte do jogador para aquele dia (de 1 a 10).

### ⚙️ Painel de Administração (Controle Total)
Comandos fáceis de usar para o dono do servidor gerenciar a economia.

* `-addmoney <@usuário> <valor>`: Adiciona dinheiro a um jogador.
* `-removemoney <@usuário> <valor>`: Remove dinheiro de um jogador.
* `-settaxa <porcentagem>`: Define a "taxa da casa" (lucro do bot) em todas as apostas (ex: 5 para 5%).
* `-setmax <valor>`: Define o valor máximo para qualquer aposta nos jogos.
* `-logs [limite]`: Mostra as últimas transações e jogos (quem ganhou, quem perdeu) direto no Discord.
* `-resetar`: Reseta **toda** a economia do servidor (requer confirmação).

### 💥 Funcionalidades Automáticas
Sistemas que rodam em segundo plano para manter o bot vivo.

* **Happy Hour:** A cada hora, há uma chance de iniciar uma "Happy Hour" de 1h, dando +30% de ganhos em todos os jogos.
* **Logs no Canal:** Todas as apostas importantes, pagamentos e comandos de admin são registrados em um canal privado de logs.
* **Anti-Spam:** Cooldowns em todos os comandos para prevenir abuso.

---

## 🛠️ Instalação e Configuração

Este bot é **self-hosted**, o que significa que você precisa rodá-lo em sua própria máquina ou em uma VPS (servidor online).

### Pré-requisitos
* [Python 3.10 ou mais recente](https://www.python.org/downloads/)
* Conhecimento básico de como usar um terminal ou linha de comando.
* Um Token de Bot do Discord (veja abaixo).

### Pacote de Arquivos
Você deve ter recebido os seguintes arquivos:
1.  `main.py` (O cérebro do bot)
2.  `database.py` (O módulo de banco de dados)
3.  `jogos_complexos.py` (O módulo de jogos avançados)
4.  `.env` (O arquivo de configuração)
5.  `requirements.txt` (As dependências)
6.  `README.md` (Este arquivo)

### Passo 1: Instalar as Dependências
Abra um terminal na pasta onde os arquivos estão e rode o seguinte comando:
```bash
pip install -r requirements.txt
