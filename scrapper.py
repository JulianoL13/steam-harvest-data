import requests
import json
import time
import logging
import argparse
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any, Set
import signal
import sys
from pathlib import Path
from collections import deque
import queue
import threading

# =====================================================
# CONFIGURAÇÃO DE LOCKS E RECURSOS COMPARTILHADOS
# =====================================================

# Lock principal para operações críticas
main_lock = threading.Lock()

# Lock específico para arquivos (evita corrupção)
file_lock = threading.Lock()

# Lock para gerenciamento de proxies
proxy_lock = threading.Lock()

# Controle de parada graceful - CORRIGIDO
stop_processing = threading.Event()
goal_reached = threading.Event()

# Configuração de logging thread-safe
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('steam_scraper.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# =====================================================
# SIGNAL HANDLER
# =====================================================

def signal_handler(sig, frame):
    logger.info("🛑 Recebido sinal de interrupção. Finalizando graciosamente...")
    stop_processing.set()
    goal_reached.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# =====================================================
# PROXY MANAGER OTIMIZADO
# =====================================================

class ProxyManager:
    """Gerenciador de proxies thread-safe com pool dedicado"""
    
    def __init__(self, proxy_file: Optional[str] = None):
        self.proxies = self._load_proxies(proxy_file)
        self.proxy_queue = queue.Queue()
        self.failed_proxies = set()
        self._init_queue()
        
    def _load_proxies(self, proxy_file: Optional[str]) -> List[str]:
        """Carrega e valida proxies"""
        if not proxy_file or not os.path.exists(proxy_file):
            return []
        
        try:
            with open(proxy_file, 'r') as f:
                content = f.read()
            
            raw_proxies = content.replace("\n", ",").split(",")
            proxies = []
            
            for p in raw_proxies:
                p = p.strip()
                if not p:
                    continue
                if not p.startswith("http"):
                    p = "https://" + p
                proxies.append(p)
            
            logger.info(f"📡 Carregados {len(proxies)} proxies válidos")
            return proxies
        except Exception as e:
            logger.error(f"❌ Erro ao carregar proxies: {e}")
            return []
    
    def _init_queue(self):
        """Inicializa fila de proxies com IP local incluído"""
        # IP local sempre disponível
        self.proxy_queue.put(None)  # None = IP local
        
        # Adiciona todos os proxies
        for proxy in self.proxies:
            self.proxy_queue.put(proxy)
    
    def get_proxy(self) -> Optional[str]:
        """Obtém próximo proxy disponível (thread-safe)"""
        try:
            proxy = self.proxy_queue.get_nowait()
            # Recoloca na fila para rotação contínua
            self.proxy_queue.put(proxy)
            return proxy
        except queue.Empty:
            # Se fila vazia, reinicializa
            self._init_queue()
            return self.get_proxy()
    
    def mark_failed(self, proxy: Optional[str]):
        """Marca proxy como falhado temporariamente"""
        if proxy:
            with proxy_lock:
                self.failed_proxies.add(proxy)
                logger.warning(f"🚫 Proxy marcado como falhado: {proxy}")
    
    def get_proxy_config(self, proxy: Optional[str]) -> Optional[Dict]:
        """Retorna configuração de proxy para requests"""
        if proxy and proxy not in self.failed_proxies:
            return {"http": proxy, "https": proxy}
        return None

# =====================================================
# CURSOR MANAGER OTIMIZADO COM RESERVA ATÔMICA
# =====================================================

class CursorManager:
    """Gerenciador de estado com reserva atômica de App IDs"""
    
    def __init__(self, cursor_file: str, progress_file: str = None):
        self.cursor_file = cursor_file
        self.progress_file = progress_file or f"{cursor_file}.progress"
        self.backup_file = f"{cursor_file}.backup"
        
        # Sets thread-safe para controle de estado
        self.processed_appids: Set[int] = set()
        self.reserved_appids: Set[int] = set()
        self.failed_appids: Set[int] = set()
        
        # Contadores
        self.total_games_found = 0
        self.last_batch_index = 0
        
    def load_state(self) -> Dict[str, Any]:
        """Carrega estado completo do cursor com backup automático"""
        state = {
            'processed_appids': set(),
            'reserved_appids': set(),
            'failed_appids': set(),
            'total_games_found': 0,
            'last_batch_index': 0
        }
        
        # Tenta carregar arquivo principal primeiro
        for file_path in [self.progress_file, self.backup_file]:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        state['processed_appids'] = set(data.get('processed_appids', []))
                        state['reserved_appids'] = set(data.get('reserved_appids', []))
                        state['failed_appids'] = set(data.get('failed_appids', []))
                        state['total_games_found'] = data.get('total_games_found', 0)
                        state['last_batch_index'] = data.get('last_batch_index', 0)
                        
                    logger.info(f"✅ Estado carregado de {file_path}: "
                              f"{len(state['processed_appids'])} processados, "
                              f"{len(state['reserved_appids'])} reservados, "
                              f"{state['total_games_found']} jogos encontrados")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao carregar {file_path}: {e}")
                    continue
        else:
            logger.info("🆕 Começando com estado limpo")
        
        self.processed_appids = state['processed_appids']
        self.reserved_appids = state['reserved_appids']
        self.failed_appids = state['failed_appids']
        self.total_games_found = state['total_games_found']
        self.last_batch_index = state['last_batch_index']
        
        return state
    
    def save_state(self, force: bool = False):
        """Salva estado com backup automático e operação atômica"""
        with main_lock:
            try:
                state = {
                    'processed_appids': list(self.processed_appids),
                    'reserved_appids': list(self.reserved_appids),
                    'failed_appids': list(self.failed_appids),
                    'total_games_found': self.total_games_found,
                    'last_batch_index': self.last_batch_index,
                    'timestamp': time.time()
                }
                
                # 1. Salva backup do arquivo atual
                if os.path.exists(self.progress_file):
                    try:
                        os.replace(self.progress_file, self.backup_file)
                    except Exception as e:
                        logger.warning(f"⚠️ Erro ao criar backup: {e}")
                
                # 2. Salva em arquivo temporário
                temp_file = f"{self.progress_file}.tmp"
                with open(temp_file, 'w') as f:
                    json.dump(state, f, indent=2)
                
                # 3. Move arquivo temporário (operação atômica)
                os.replace(temp_file, self.progress_file)
                
                if force:
                    logger.info(f"💾 Estado salvo: {len(self.processed_appids)} processados, "
                              f"{len(self.reserved_appids)} reservados")
                    
            except Exception as e:
                logger.error(f"❌ ERRO CRÍTICO ao salvar estado: {e}")
                # Tenta restaurar backup se algo deu errado
                if os.path.exists(self.backup_file):
                    try:
                        os.replace(self.backup_file, self.progress_file)
                        logger.info("🔄 Backup restaurado")
                    except Exception as restore_e:
                        logger.error(f"❌ Erro ao restaurar backup: {restore_e}")
    
    def reserve_appid(self, appid: int) -> bool:
        """RESERVA App ID de forma atômica - THREAD-SAFE"""
        with main_lock:
            # Verifica se já foi processado ou reservado
            if (appid in self.processed_appids or 
                appid in self.reserved_appids or 
                appid in self.failed_appids):
                return False
            
            # Reserva o App ID
            self.reserved_appids.add(appid)
            logger.debug(f"🔒 App ID {appid} RESERVADO")
            return True
    
    def mark_processed(self, appid: int, success: bool = True):
        """Marca App ID como processado e remove da reserva"""
        with main_lock:
            # Remove da reserva
            self.reserved_appids.discard(appid)
            
            if success:
                self.processed_appids.add(appid)
                self.failed_appids.discard(appid)
                # Removido incremento aqui - será feito em outro lugar
                logger.debug(f"✅ App ID {appid} processado com SUCESSO")
            else:
                self.failed_appids.add(appid)
                logger.debug(f"❌ App ID {appid} processado com FALHA")
    
    def release_reservation(self, appid: int):
        """Libera reserva de App ID (em caso de erro antes de processar)"""
        with main_lock:
            self.reserved_appids.discard(appid)
            logger.debug(f"🔓 Reserva liberada para App ID {appid}")
    
    def get_remaining_games(self, all_games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Retorna jogos não processados, não reservados e não falhados"""
        remaining = []
        all_blocked = self.processed_appids | self.reserved_appids
        
        for game in all_games:
            appid = game.get('appid')
            if appid and appid not in all_blocked:
                remaining.append(game)
        
        logger.info(f"📋 Jogos restantes: {len(remaining)}/{len(all_games)} "
                   f"(Processados: {len(self.processed_appids)}, "
                   f"Reservados: {len(self.reserved_appids)})")
        return remaining

# =====================================================
# CONTADOR THREAD-SAFE CORRIGIDO
# =====================================================

class ThreadSafeCounter:
    """Contador thread-safe com limite dinâmico"""
    
    def __init__(self, initial: int = 0, max_value: int = None):
        self._value = initial
        self._max_value = max_value
        self._lock = threading.Lock()
    
    def increment(self) -> tuple[bool, int]:
        """Incrementa contador se não exceder limite. Retorna (sucesso, valor_atual)"""
        with self._lock:
            if self._max_value and self._value >= self._max_value:
                return False, self._value
            self._value += 1
            return True, self._value
    
    def decrement(self) -> int:
        """Decrementa contador"""
        with self._lock:
            self._value = max(0, self._value - 1)
            return self._value
    
    @property
    def value(self) -> int:
        """Obtém valor atual (thread-safe)"""
        with self._lock:
            return self._value
    
    def set_max(self, max_value: int):
        """Define valor máximo"""
        with self._lock:
            self._max_value = max_value
    
    def reached_limit(self) -> bool:
        """Verifica se atingiu limite"""
        with self._lock:
            return self._max_value and self._value >= self._max_value

# =====================================================
# UTILS OTIMIZADOS
# =====================================================

def make_request(url: str, params: Optional[Dict] = None, timeout: int = 15, 
                proxies: Optional[Dict] = None, retries: int = 3) -> Optional[requests.Response]:
    """Request com retry exponential backoff otimizado"""
    for attempt in range(retries):
        if stop_processing.is_set() or goal_reached.is_set():
            return None
            
        try:
            response = requests.get(url, params=params, timeout=timeout, 
                                  proxies=proxies, allow_redirects=True)
            
            if response.status_code == 429:
                wait_time = min((2 ** attempt) + random.uniform(0, 1), 10)
                logger.warning(f"⏱️ Rate limit - aguardando {wait_time:.2f}s")
                time.sleep(wait_time)
                continue
                
            response.raise_for_status()
            return response
            
        except requests.RequestException as e:
            if attempt == retries - 1:
                logger.debug(f"🔌 Request falhou após {retries} tentativas: {e}")
                return None
            time.sleep(min(0.5 * (attempt + 1), 3))
    
    return None

def safe_save_jsonl(record: Dict[str, Any], filename: str) -> bool:
    """Salva record em JSONL com lock thread-safe e verificação de integridade"""
    with file_lock:
        try:
            # Serializa primeiro para validar JSON
            json_record = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
            
            # Salva com newline
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(json_record + '\n')
                f.flush()  # Force write to disk
            
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao salvar em {filename}: {e}")
            return False

def get_existing_appids(filename: str) -> Set[int]:
    """Extrai App IDs existentes com validação robusta"""
    appids = set()
    if not os.path.exists(filename):
        return appids
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            line_count = 0
            for line in f:
                line_count += 1
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    record = json.loads(line)
                    appid = record.get('appid')
                    if appid and isinstance(appid, int):
                        appids.add(appid)
                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️ Linha {line_count} inválida em {filename}: {e}")
                    continue
        
        logger.info(f"📊 {len(appids)} App IDs existentes em {filename}")
        
    except Exception as e:
        logger.error(f"❌ Erro ao ler {filename}: {e}")
    
    return appids

# =====================================================
# STEAM API OTIMIZADA
# =====================================================

def get_all_game_list() -> List[Dict[str, Any]]:
    """Obtém lista completa de jogos com retry robusto"""
    url = "https://api.steampowered.com/ISteamApps/GetAppList/v2"
    
    for attempt in range(3):
        response = make_request(url, timeout=30, retries=2)
        if response:
            try:
                data = response.json()
                apps = data.get('applist', {}).get('apps', [])
                logger.info(f"📦 {len(apps)} jogos obtidos da Steam API")
                return apps
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"❌ Erro ao processar resposta da API: {e}")
                
        if attempt < 2:
            wait_time = 5 * (attempt + 1)
            logger.warning(f"🔄 Tentativa {attempt + 1} falhou, aguardando {wait_time}s...")
            time.sleep(wait_time)
    
    logger.error("❌ Falha ao obter lista de jogos após todas as tentativas")
    return []

def get_app_details(appid: int, proxy_manager: ProxyManager) -> Optional[Dict[str, Any]]:
    """Obtém detalhes com pool de proxies otimizado"""
    if goal_reached.is_set() or stop_processing.is_set():
        return None
        
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english"
    
    for attempt in range(4):  # Máximo 4 tentativas
        if stop_processing.is_set() or goal_reached.is_set():
            return None
        
        proxy = proxy_manager.get_proxy()
        proxy_config = proxy_manager.get_proxy_config(proxy)
        proxy_str = proxy or 'IP_LOCAL'
        
        response = make_request(url, timeout=12, proxies=proxy_config, retries=1)
        
        if response:
            try:
                data = response.json()
                app_data = data.get(str(appid))
                
                if app_data and app_data.get('success'):
                    return app_data.get('data')
                else:
                    return None  # App não disponível
                    
            except json.JSONDecodeError:
                logger.debug(f"🔴 App {appid}: JSON inválido via {proxy_str}")
                if proxy:
                    proxy_manager.mark_failed(proxy)
                continue
        else:
            logger.debug(f"🔴 App {appid}: sem resposta via {proxy_str}")
            if proxy:
                proxy_manager.mark_failed(proxy)
    
    return None

def get_app_reviews(appid: int, num_reviews: int, proxy_manager: ProxyManager) -> List[Dict[str, Any]]:
    """Obtém reviews com paginação eficiente"""
    if goal_reached.is_set() or stop_processing.is_set():
        return []
        
    reviews = []
    cursor = '*'
    max_pages = min(10, (num_reviews + 99) // 100)  # Limita páginas
    
    for page in range(max_pages):
        if stop_processing.is_set() or goal_reached.is_set() or len(reviews) >= num_reviews:
            break
            
        proxy = proxy_manager.get_proxy()
        proxy_config = proxy_manager.get_proxy_config(proxy)
        
        num_to_fetch = min(100, num_reviews - len(reviews))
        params = {
            'json': 1,
            'purchase_type': 'all',
            'num_per_page': num_to_fetch,
            'cursor': cursor,
            'filter': 'recent'
        }
        
        url = f"https://store.steampowered.com/appreviews/{appid}"
        response = make_request(url, params=params, timeout=12, proxies=proxy_config, retries=1)
        
        if response:
            try:
                data = response.json()
                if data.get('success') and data.get('reviews'):
                    new_reviews = data['reviews']
                    reviews.extend(new_reviews)
                    
                    cursor = data.get('cursor')
                    if not cursor or not new_reviews:
                        break
                else:
                    break
                    
            except json.JSONDecodeError:
                break
        else:
            if proxy:
                proxy_manager.mark_failed(proxy)
            break
            
        # Pausa entre requests de reviews
        time.sleep(0.2)
    
    return reviews[:num_reviews]

# =====================================================
# PROCESSAMENTO CORRIGIDO E THREAD-SAFE
# =====================================================

def processar_um_jogo(app: Dict[str, Any], proxy_manager: ProxyManager, 
                     game_details_file: str, game_reviews_file: str, 
                     args: argparse.Namespace, cursor_manager: CursorManager,
                     games_counter: ThreadSafeCounter) -> bool:
    """
    Processa um jogo com reserva atômica - TOTALMENTE THREAD-SAFE CORRIGIDO
    """
    if stop_processing.is_set() or goal_reached.is_set():
        return False
    
    appid = app.get('appid')
    if not appid:
        return False
    
    # ====== RESERVA ATÔMICA - EVITA DUPLICAÇÃO ======
    if not cursor_manager.reserve_appid(appid):
        logger.debug(f"App {appid} já reservado/processado, pulando...")
        return False
    
    # ====== VERIFICAÇÃO PRECOCE DO LIMITE ======
    if games_counter.reached_limit():
        cursor_manager.release_reservation(appid)
        if not goal_reached.is_set():
            goal_reached.set()
            logger.info(f"🎯 META DE {args.max_games} JOGOS ATINGIDA! Finalizando...")
        return False
    
    try:
        # Obtém detalhes do app
        details = get_app_details(appid, proxy_manager)
        
        if not details or goal_reached.is_set():
            cursor_manager.mark_processed(appid, success=False)
            return False
            
        # Validações de qualidade
        if not _is_valid_game(details):
            cursor_manager.mark_processed(appid, success=False)
            return False
        
        # ====== RESERVA SLOT NO CONTADOR (ATÔMICO) ======
        success, current_count = games_counter.increment()
        
        if not success or goal_reached.is_set():
            # Limite atingido ou processo sendo finalizado
            cursor_manager.mark_processed(appid, success=False)
            if not goal_reached.is_set():
                goal_reached.set()
                logger.info(f"🎯 META DE {args.max_games} JOGOS ATINGIDA! Finalizando...")
            return False
        
        game_name = details.get('name', 'Nome não disponível')
        logger.info(f"🎮 JOGO VÁLIDO [{current_count}/{args.max_games}]: {appid} - {game_name}")
        
        # Adiciona appid e salva detalhes
        details['appid'] = appid
        if not safe_save_jsonl(details, game_details_file):
            # Se falhou ao salvar, reverte contador
            games_counter.decrement()
            cursor_manager.mark_processed(appid, success=False)
            return False
        
        # Processa reviews se solicitado
        reviews_saved = 0
        if args.max_reviews > 0 and not goal_reached.is_set():
            reviews = get_app_reviews(appid, args.max_reviews, proxy_manager)
            
            for review in reviews:
                if stop_processing.is_set() or goal_reached.is_set():
                    break
                review['appid'] = appid
                if safe_save_jsonl(review, game_reviews_file):
                    reviews_saved += 1
            
            logger.info(f"📝 {reviews_saved} reviews salvos para {appid}")
        
        # Marca como processado com sucesso
        cursor_manager.mark_processed(appid, success=True)
        
        # VERIFICA SE ATINGIU META FINAL
        if games_counter.reached_limit() and not goal_reached.is_set():
            goal_reached.set()
            logger.info(f"🎯 META DE {args.max_games} JOGOS ATINGIDA! Processo finalizado.")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ ERRO ao processar app {appid}: {e}")
        
        # Limpa recursos em caso de erro
        cursor_manager.release_reservation(appid)
        # Se havia incrementado contador, decrementa
        games_counter.decrement()
        return False

def _is_valid_game(details: Dict[str, Any]) -> bool:
    """Valida se é um jogo de qualidade"""
    # Deve ser do tipo 'game'
    if details.get('type') != 'game':
        return False
        
    # Deve ter nome
    if not details.get('name'):
        return False
        
    # Não deve ser DLC
    categories = details.get('categories', [])
    if any(cat.get('id') == 21 for cat in categories if isinstance(cat, dict)):
        return False
        
    # Filtros adicionais de qualidade podem ser adicionados aqui
    
    return True

# =====================================================
# PROGRESS TRACKER OTIMIZADO
# =====================================================

class ProgressTracker:
    """Tracker de progresso thread-safe com ETA"""
    
    def __init__(self, total_target: int):
        self.total_target = total_target
        self.start_time = time.time()
        self.last_update = time.time()
        self._lock = threading.Lock()
        
    def update(self, games_found: int, apps_processed: int = None):
        """Atualiza e exibe progresso (thread-safe)"""
        current_time = time.time()
        
        with self._lock:
            if current_time - self.last_update > 20:  # Update a cada 20s
                elapsed = current_time - self.start_time
                
                if games_found > 0:
                    rate = games_found / elapsed * 60  # jogos por minuto
                    remaining = self.total_target - games_found
                    eta_minutes = remaining / rate if rate > 0 else 0
                    
                    percentage = games_found / self.total_target * 100
                    
                    logger.info(f"📊 PROGRESSO: {games_found}/{self.total_target} jogos "
                              f"({percentage:.1f}%) | Taxa: {rate:.1f}/min | "
                              f"ETA: {eta_minutes:.0f}min")
                
                self.last_update = current_time

# =====================================================
# FUNÇÃO PRINCIPAL CORRIGIDA
# =====================================================

def main(args=None):
    """Função principal otimizada e thread-safe"""
    
    if args is None:
        parser = argparse.ArgumentParser(description="🚀 Steam Scraper Otimizado e Thread-Safe")
        parser.add_argument('--proxies', type=str, help='Arquivo com lista de proxies')
        parser.add_argument('--max_games', type=int, default=10, help='Número máximo de jogos válidos')
        parser.add_argument('--max_reviews', type=int, default=10, help='Reviews por jogo')
        parser.add_argument('--cursor_file', type=str, default='scraper_cursor.txt')
        parser.add_argument('--reset_cursor', action='store_true', help='Reseta cursor e recomeça')
        parser.add_argument('--game_details_file', type=str, default='game_details.jsonl')
        parser.add_argument('--game_reviews_file', type=str, default='game_reviews.jsonl')
        parser.add_argument('--parallel', action='store_true', help='Modo paralelo (recomendado)')
        parser.add_argument('--workers', type=int, default=8, help='Threads no modo paralelo')
        parser.add_argument('--batch_size', type=int, default=100, help='Tamanho do lote - REDUZIDO')
        parser.add_argument('--checkpoint_interval', type=int, default=25, help='Intervalo para salvar estado')
        args = parser.parse_args()

    # Validação e ajuste de argumentos
    args.max_games = max(1, args.max_games)
    args.max_reviews = max(0, args.max_reviews)
    args.workers = max(1, min(20, args.workers))
    args.checkpoint_interval = max(5, args.checkpoint_interval)
    args.batch_size = max(50, min(150, args.batch_size))  # Limita batch size
    
    logger.info(f"🚀 INICIANDO Steam Scraper Otimizado")
    logger.info(f"🎯 Meta: {args.max_games} jogos | Reviews: {args.max_reviews} por jogo")
    logger.info(f"🔧 Modo: {'PARALELO' if args.parallel else 'SEQUENCIAL'} | Workers: {args.workers}")
    
    # Inicializa gerenciadores
    cursor_manager = CursorManager(args.cursor_file)
    proxy_manager = ProxyManager(args.proxies)
    
    # Reset cursor se solicitado
    if args.reset_cursor:
        for file in [cursor_manager.cursor_file, cursor_manager.progress_file, cursor_manager.backup_file]:
            if os.path.exists(file):
                os.remove(file)
                logger.info(f"🗑️ Removido: {file}")
    
    # Carrega estado anterior
    cursor_manager.load_state()
    
    # Obtém lista de jogos
    logger.info("📦 Obtendo lista de jogos da Steam...")
    all_games = get_all_game_list()
    if not all_games:
        logger.error("❌ Não foi possível obter a lista de jogos")
        return

    # Carrega App IDs existentes e atualiza cursor
    existing_details = get_existing_appids(args.game_details_file)
    for appid in existing_details:
        cursor_manager.processed_appids.add(appid)
    
    # Atualiza contador de jogos encontrados
    cursor_manager.total_games_found = len(existing_details)
    
    # Filtra jogos restantes
    remaining_games = cursor_manager.get_remaining_games(all_games)
    
    if not remaining_games:
        logger.info("✅ Todos os jogos já foram processados!")
        return
    
    # Ajusta meta
    games_already_found = cursor_manager.total_games_found
    games_needed = max(0, args.max_games - games_already_found)
    
    logger.info(f"📊 Status: {games_already_found} já encontrados, {games_needed} ainda necessários")
    
    if games_needed <= 0:
        logger.info("🎉 Meta já atingida!")
        return
    
    # Embaralha para distribuição aleatória
    random.shuffle(remaining_games)
    
    # Inicializa controles CORRIGIDOS
    progress_tracker = ProgressTracker(args.max_games)
    games_counter = ThreadSafeCounter(games_already_found, args.max_games)  # CONTADOR THREAD-SAFE
    
    checkpoint_counter = 0
    processed_count = 0
    
    try:
        if not args.parallel:
            # ===== MODO SEQUENCIAL =====
            logger.info("🔄 Executando em modo SEQUENCIAL")
            
            for i, app in enumerate(remaining_games):
                if stop_processing.is_set() or goal_reached.is_set():
                    logger.info("🛑 Processamento interrompido")
                    break
                    
                if games_counter.reached_limit():
                    logger.info(f"🎯 Meta de {args.max_games} jogos atingida!")
                    break
                
                if processar_um_jogo(app, proxy_manager, args.game_details_file, 
                                   args.game_reviews_file, args, cursor_manager, games_counter):
                    logger.info(f"📈 Progresso: {games_counter.value}/{args.max_games} jogos")
                
                processed_count += 1
                checkpoint_counter += 1
                
                # Checkpoint periódico
                if checkpoint_counter >= args.checkpoint_interval:
                    cursor_manager.save_state(force=True)
                    progress_tracker.update(games_counter.value, processed_count)
                    checkpoint_counter = 0
                    
        else:
            # ===== MODO PARALELO CORRIGIDO COM CONTROLE RIGOROSO =====
            logger.info(f"⚡ Executando em modo PARALELO com {args.workers} workers")
            
            with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="Worker") as executor:
                
                # Processa em batches menores para melhor controle
                for batch_start in range(0, len(remaining_games), args.batch_size):
                    if stop_processing.is_set() or goal_reached.is_set():
                        logger.info("🛑 Meta atingida ou processamento interrompido - parando batches")
                        break
                    
                    batch_end = min(batch_start + args.batch_size, len(remaining_games))
                    batch = remaining_games[batch_start:batch_end]
                    
                    batch_num = batch_start // args.batch_size + 1
                    logger.info(f"🔄 Batch {batch_num}: processando {len(batch)} jogos "
                              f"[{games_counter.value}/{args.max_games} encontrados]")
                    
                    # Submete tasks do batch
                    futures = []
                    for app in batch:
                        # Verifica limite antes de submeter CADA task
                        if games_counter.reached_limit() or goal_reached.is_set():
                            logger.info(f"🎯 Meta atingida - não submetendo mais tasks")
                            break
                        
                        future = executor.submit(
                            processar_um_jogo,
                            app,
                            proxy_manager,
                            args.game_details_file,
                            args.game_reviews_file,
                            args,
                            cursor_manager,
                            games_counter
                        )
                        futures.append(future)
                    
                    if not futures:  # Sem tasks submetidas
                        break
                    
                    # Processa resultados conforme completam
                    completed_count = 0
                    for future in as_completed(futures):
                        if stop_processing.is_set() or goal_reached.is_set():
                            # Cancela futures restantes
                            for f in futures:
                                if not f.done():
                                    f.cancel()
                            logger.info("🛑 Meta atingida - cancelando tasks restantes do batch")
                            break
                        
                        try:
                            result = future.result(timeout=45)  # Timeout aumentado
                            completed_count += 1
                            
                            if result:  # Jogo válido processado
                                current_count = games_counter.value
                                logger.info(f"📈 [{current_count}/{args.max_games}] jogos encontrados")
                                
                                # VERIFICA META IMEDIATAMENTE
                                if games_counter.reached_limit():
                                    logger.info(f"🎯 META DE {args.max_games} ATINGIDA! Cancelando tasks restantes...")
                                    goal_reached.set()
                                    
                                    # Cancela todas as futures restantes
                                    for f in futures:
                                        if not f.done():
                                            f.cancel()
                                    break
                        
                        except Exception as exc:
                            logger.error(f"❌ Erro em task: {exc}")
                        
                        processed_count += 1
                        checkpoint_counter += 1
                        
                        # Checkpoint periódico
                        if checkpoint_counter >= args.checkpoint_interval:
                            cursor_manager.save_state()
                            progress_tracker.update(games_counter.value, processed_count)
                            checkpoint_counter = 0
                    
                    logger.info(f"✅ Batch {batch_num} concluído: {completed_count}/{len(futures)} tasks processadas")
                    
                    # VERIFICA META APÓS CADA BATCH
                    if games_counter.reached_limit() or goal_reached.is_set():
                        logger.info("🎯 Meta atingida - finalizando processamento em batches")
                        break
                    
                    # Pequena pausa entre batches para não sobrecarregar
                    time.sleep(0.5)
        
        # Aguarda um momento para threads finalizarem completamente
        if goal_reached.is_set():
            logger.info("⏳ Aguardando finalização de threads...")
            time.sleep(3)  # Pausa para threads terminarem graciosamente
        
        # Salva estado final
        cursor_manager.save_state(force=True)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Interrompido pelo usuário")
        stop_processing.set()
        goal_reached.set()
        
    except Exception as e:
        logger.error(f"❌ ERRO CRÍTICO: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        
    finally:
        # FORÇA PARADA DE TODAS AS THREADS
        stop_processing.set()
        goal_reached.set()
        
        # Aguarda um pouco para threads finalizarem
        time.sleep(1)
        
        # Garantia de salvar estado final
        try:
            cursor_manager.save_state(force=True)
        except Exception as save_error:
            logger.error(f"❌ Erro ao salvar estado final: {save_error}")
    
    # ===== RELATÓRIO FINAL =====
    final_games_found = games_counter.value
    total_processed = len(cursor_manager.processed_appids)
    total_failed = len(cursor_manager.failed_appids)
    total_reserved = len(cursor_manager.reserved_appids)
    
    logger.info(f"")
    logger.info(f"🏁 ===== PROCESSO FINALIZADO =====")
    logger.info(f"🎮 Jogos válidos encontrados: {final_games_found}")
    logger.info(f"📊 Total de App IDs processados: {total_processed}")
    logger.info(f"❌ App IDs que falharam: {total_failed}")
    logger.info(f"🔒 App IDs ainda reservados: {total_reserved}")
    logger.info(f"📁 Detalhes salvos em: {args.game_details_file}")
    logger.info(f"📝 Reviews salvos em: {args.game_reviews_file}")
    
    if final_games_found >= args.max_games:
        logger.info(f"🎉 META DE {args.max_games} JOGOS ATINGIDA COM SUCESSO!")
    else:
        logger.info(f"⚠️ Meta parcialmente atingida: {final_games_found}/{args.max_games}")
    
    if total_failed > 0:
        logger.info(f"🔄 Para reprocessar falhas, delete o arquivo de progresso e execute novamente")
    
    if total_reserved > 0:
        logger.warning(f"⚠️ {total_reserved} App IDs ficaram reservados (possível interrupção)")
        logger.info("💡 Execute novamente para processar os reservados")
    
    logger.info(f"✨ Scraper finalizado!")

if __name__ == "__main__":
    main()