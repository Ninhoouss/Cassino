# database.py
import sqlite3
import datetime

DB_NAME = "cassino.db"

# --- 3. Funções do Banco de Dados (SQLite) ---
print("Configurando funções de banco de dados...")

def init_db():
    """Cria todas as tabelas necessárias no banco de dados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        user_id INTEGER PRIMARY KEY,
        carteira INTEGER DEFAULT 100,
        banco INTEGER DEFAULT 0,
        daily_streak INTEGER DEFAULT 0,
        last_daily TEXT DEFAULT '2000-01-01 00:00:00' 
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stats (
        user_id INTEGER PRIMARY KEY,
        vitorias INTEGER DEFAULT 0,
        derrotas INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES usuarios (user_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_config (
        config_key TEXT PRIMARY KEY,
        config_value TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        details TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    default_config = [
        ('jackpot', '100000'), ('taxa_casa', '0.05'),
        ('max_aposta', '50000'), ('taxa_jackpot', '0.01')
    ]
    cursor.executemany("INSERT OR IGNORE INTO bot_config (config_key, config_value) VALUES (?, ?)", default_config)

    conn.commit()
    conn.close()
    print("Banco de dados inicializado.")

async def check_user(user_id: int):
    """Verifica se um usuário existe no DB. Se não, cria um registro."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO usuarios (user_id, carteira) VALUES (?, ?)", (user_id, 100))

    cursor.execute("SELECT * FROM stats WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO stats (user_id) VALUES (?)", (user_id,))

    conn.commit()
    conn.close()

def get_balance(user_id: int):
    """Pega o saldo (carteira e banco) de um usuário."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT carteira, banco FROM usuarios WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    conn.close()
    if data:
        return {'carteira': data[0], 'banco': data[1]}
    return None

def update_balance(user_id: int, carteira: int, banco: int):
    """Atualiza o saldo (carteira e banco) de um usuário."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET carteira = ?, banco = ? WHERE user_id = ?", (carteira, banco, user_id))
    conn.commit()
    conn.close()

async def update_stats(user_id: int, vitorias_add: int = 0, derrotas_add: int = 0):
    """Adiciona vitórias ou derrotas às estatísticas de um usuário."""
    await check_user(user_id)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE stats SET vitorias = vitorias + ?, derrotas = derrotas + ? WHERE user_id = ?",
        (vitorias_add, derrotas_add, user_id)
    )
    conn.commit()
    conn.close()

def get_config(config_key: str):
    """Busca um valor da tabela de configuração do bot."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT config_value FROM bot_config WHERE config_key = ?", (config_key,))
    data = cursor.fetchone()
    conn.close()
    return data[0] if data else None

def update_config(config_key: str, config_value: str):
    """Atualiza um valor na tabela de configuração do bot."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE bot_config SET config_value = ? WHERE config_key = ?", (config_value, config_key))
    conn.commit()
    conn.close()

async def db_log(user_id: int, action: str, details: str):
    """Insere um registro na tabela de logs do DB."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)", (user_id, action, details))
    conn.commit()
    conn.close()

async def get_db_logs(limit: int = 15):
    """Busca os últimos N logs do banco de dados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, user_id, action, details FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    logs = cursor.fetchall()
    conn.close()
    return logs

async def reset_economy():
    """Reseta as tabelas usuarios e stats e os configs do bot."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios")
    cursor.execute("DELETE FROM stats")
    conn.commit()
    conn.close()

    # Reseta configs para o padrão
    update_config('jackpot', '100000')
    update_config('max_aposta', '50000')

print("[database.py] Funções de banco de dados prontas.")
