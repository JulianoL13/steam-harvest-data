#!/usr/bin/env python3
"""
Script para limpar e estruturar dados do Steam scraper para análise
Converte dados JSONL para CSVs limpos e organizados
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
import argparse
import pandas as pd
from tqdm import tqdm
import logging

def clean_text(text: str) -> str:
    """Remove HTML tags e limpa texto"""
    if not text or not isinstance(text, str):
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove múltiplos espaços
    text = re.sub(r'\s+', ' ', text)
    # Remove quebras de linha
    text = text.replace('\n', ' ').replace('\r', ' ')
    return text.strip()

def extract_price_info(price_overview: Dict) -> Dict[str, Any]:
    """Extrai informações de preço de forma limpa"""
    if not price_overview:
        return {
            'currency': '',
            'original_price': 0,
            'final_price': 0,
            'discount_percent': 0,
            'is_free': True
        }
    
    return {
        'currency': price_overview.get('currency', ''),
        'original_price': price_overview.get('initial', 0) / 100 if price_overview.get('initial') else 0,
        'final_price': price_overview.get('final', 0) / 100 if price_overview.get('final') else 0,
        'discount_percent': price_overview.get('discount_percent', 0),
        'is_free': price_overview.get('final', 0) == 0
    }

def discover_all_categories(input_file: str) -> Dict[int, str]:
    """Descobre todas as categorias presentes nos dados"""
    print("🔍 Descobrindo todas as categorias nos dados...")
    categories_map = {}
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            try:
                game = json.loads(line)
                categories = game.get('categories', [])
                
                if categories:
                    for cat in categories:
                        if isinstance(cat, dict):
                            cat_id = cat.get('id')
                            cat_desc = cat.get('description', '')
                            if cat_id and cat_desc:
                                categories_map[cat_id] = cat_desc
                                
            except (json.JSONDecodeError, Exception):
                continue
    
    print(f"✅ Encontradas {len(categories_map)} categorias únicas")
    return categories_map

def extract_categories_dynamic(categories: List[Dict], all_categories: Dict[int, str]) -> Dict[str, bool]:
    """Extrai todas as categorias de forma dinâmica"""
    if not categories:
        return {f"category_{cat_id}_{clean_category_name(desc)}": False 
                for cat_id, desc in all_categories.items()}
    
    category_ids = [cat.get('id') for cat in categories if isinstance(cat, dict) and cat.get('id')]
    
    result = {}
    for cat_id, desc in all_categories.items():
        column_name = f"category_{cat_id}_{clean_category_name(desc)}"
        result[column_name] = cat_id in category_ids
    
    return result

def clean_category_name(category_desc: str) -> str:
    """Limpa nome da categoria para usar como nome de coluna"""
    if not category_desc:
        return "unknown"
    
    # Remove caracteres especiais e espaços
    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', category_desc)
    # Substitui espaços por underscores e converte para minúsculas
    clean_name = re.sub(r'\s+', '_', clean_name.strip().lower())
    return clean_name

def discover_all_genres(input_file: str) -> Dict[int, str]:
    """Descobre todos os gêneros presentes nos dados"""
    print("🔍 Descobrindo todos os gêneros nos dados...")
    genres_map = {}
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            try:
                game = json.loads(line)
                genres = game.get('genres', [])
                
                if genres:
                    for genre in genres:
                        if isinstance(genre, dict):
                            genre_id = genre.get('id')
                            genre_desc = genre.get('description', '')
                            if genre_id and genre_desc:
                                genres_map[genre_id] = genre_desc
                                
            except (json.JSONDecodeError, Exception):
                continue
    
    print(f"✅ Encontrados {len(genres_map)} gêneros únicos")
    return genres_map

def extract_genres_dynamic(genres: List[Dict], all_genres: Dict[int, str]) -> Dict[str, bool]:
    """Extrai todos os gêneros de forma dinâmica"""
    if not genres:
        return {f"genre_{genre_id}_{clean_category_name(desc)}": False 
                for genre_id, desc in all_genres.items()}
    
    genre_ids = [genre.get('id') for genre in genres if isinstance(genre, dict) and genre.get('id')]
    
    result = {}
    for genre_id, desc in all_genres.items():
        column_name = f"genre_{genre_id}_{clean_category_name(desc)}"
        result[column_name] = genre_id in genre_ids
    
    return result

def extract_genres(genres: List[Dict]) -> List[str]:
    """Extrai lista de gêneros"""
    if not genres:
        return []
    return [genre.get('description', '') for genre in genres if isinstance(genre, dict)]

def extract_platforms(platforms: Dict) -> Dict[str, bool]:
    """Extrai informações de plataformas"""
    if not platforms:
        return {'windows': False, 'mac': False, 'linux': False}
    
    return {
        'windows': platforms.get('windows', False),
        'mac': platforms.get('mac', False),
        'linux': platforms.get('linux', False)
    }

def clean_game_details(input_file: str, output_file: str, columns=None, export_format='csv'):
    """Limpa dados de detalhes dos jogos"""
    logging.info(f"Limpando dados de jogos: {input_file} -> {output_file}")
    print(f"🧹 Limpando dados de jogos: {input_file} -> {output_file}")
    all_categories = discover_all_categories(input_file)
    all_genres = discover_all_genres(input_file)
    logging.info(f"Categorias encontradas: {list(all_categories.values())}")
    logging.info(f"Gêneros encontrados: {list(all_genres.values())}")
    print(f"📊 Categorias encontradas: {list(all_categories.values())}")
    print(f"📊 Gêneros encontrados: {list(all_genres.values())}")

    cleaned_games = []
    error_lines = []
    chunk_size = 10000
    chunk_games = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(tqdm(f, desc="Processando jogos"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                game = json.loads(line)
                price_info = extract_price_info(game.get('price_overview'))
                categories_info = extract_categories_dynamic(game.get('categories', []), all_categories)
                genres_info = extract_genres_dynamic(game.get('genres', []), all_genres)
                genres = extract_genres(game.get('genres', []))
                platforms = extract_platforms(game.get('platforms', {}))
                release_date = game.get('release_date', {})
                release_date_str = release_date.get('date', '') if isinstance(release_date, dict) else ''
                coming_soon = release_date.get('coming_soon', False) if isinstance(release_date, dict) else False
                cleaned_game = {
                    'appid': game.get('appid'),
                    'name': str(game.get('name', '') or '').strip(),
                    'type': str(game.get('type', '') or '').strip(),
                    'short_description': str(game.get('short_description', '') or '').strip()[:500],
                    'currency': price_info['currency'],
                    'original_price': price_info['original_price'],
                    'final_price': price_info['final_price'],
                    'discount_percent': price_info['discount_percent'],
                    'is_free': price_info['is_free'],
                    'required_age': game.get('required_age', 0),
                    'genres': ', '.join(genres),
                    'genre_count': len(genres),
                    'windows': platforms['windows'],
                    'mac': platforms['mac'],
                    'linux': platforms['linux'],
                    'platform_count': sum(platforms.values()),
                    'release_date': release_date_str,
                    'coming_soon': coming_soon,
                    'developers': ', '.join(game.get('developers', [])) if game.get('developers') else '',
                    'publishers': ', '.join(game.get('publishers', [])) if game.get('publishers') else '',
                    'screenshot_count': len(game.get('screenshots', [])),
                    'movie_count': len(game.get('movies', [])),
                    'has_website': bool(str(game.get('website', '') or '').strip()),
                    'supported_languages_count': len(str(game.get('supported_languages', '') or '').split(',')) if game.get('supported_languages') else 0
                }
                cleaned_game.update(categories_info)
                cleaned_game.update(genres_info)
                chunk_games.append(cleaned_game)
                if len(chunk_games) >= chunk_size:
                    df_chunk = pd.DataFrame(chunk_games)
                    df_chunk = df_chunk.drop_duplicates(subset=["appid"])
                    cleaned_games.append(df_chunk)
                    chunk_games = []
            except Exception as e:
                print(f"⚠️ Erro processando linha {line_num}: {e}")
                logging.warning(f"Erro processando linha {line_num}: {e}")
                error_lines.append({'line_num': line_num, 'error': str(e), 'line': line})
                continue
    # Processa o último chunk
    if chunk_games:
        df_chunk = pd.DataFrame(chunk_games)
        df_chunk = df_chunk.drop_duplicates(subset=["appid"])
        cleaned_games.append(df_chunk)
    if cleaned_games:
        df = pd.concat(cleaned_games, ignore_index=True)
        before = len(df)
        df = df.drop_duplicates(subset=["appid"])
        after = len(df)
        # Seleciona colunas se especificado
        if columns:
            df = df[[col for col in columns if col in df.columns]]
        # Exporta no formato desejado
        if export_format == 'csv':
            df.to_csv(output_file, index=False)
        elif export_format == 'parquet':
            df.to_parquet(output_file, index=False)
        elif export_format == 'feather':
            df.to_feather(output_file)
        print(f"✅ {after} jogos limpos salvos em {output_file} (removidos {before-after} duplicados)")
        logging.info(f"{after} jogos limpos salvos em {output_file} (removidos {before-after} duplicados)")
    else:
        print("❌ Nenhum jogo válido encontrado")
        logging.error("Nenhum jogo válido encontrado")
    if error_lines:
        error_file = output_file.replace('.csv', '_errors.jsonl').replace('.parquet', '_errors.jsonl').replace('.feather', '_errors.jsonl')
        with open(error_file, 'w', encoding='utf-8') as ef:
            for err in error_lines:
                ef.write(json.dumps(err, ensure_ascii=False) + '\n')
        print(f"⚠️ {len(error_lines)} linhas problemáticas salvas em {error_file}")
        logging.warning(f"{len(error_lines)} linhas problemáticas salvas em {error_file}")

def clean_reviews(input_file: str, output_file: str, columns=None, export_format='csv'):
    """Limpa dados de reviews"""
    logging.info(f"Limpando dados de reviews: {input_file} -> {output_file}")
    print(f"🧹 Limpando dados de reviews: {input_file} -> {output_file}")
    
    cleaned_reviews = []
    error_lines = []
    chunk_size = 10000
    chunk_reviews = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(tqdm(f, desc="Processando reviews"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                review = json.loads(line)
                author = review.get('author', {})
                created_timestamp = review.get('timestamp_created', 0)
                updated_timestamp = review.get('timestamp_updated', 0)
                created_date = datetime.fromtimestamp(created_timestamp).strftime('%Y-%m-%d') if created_timestamp else ''
                updated_date = datetime.fromtimestamp(updated_timestamp).strftime('%Y-%m-%d') if updated_timestamp else ''
                review_text = clean_text(review.get('review', ''))
                word_count = len(review_text.split()) if review_text else 0
                char_count = len(review_text)
                
                def safe_round(val, ndigits=0):
                    try:
                        if isinstance(val, str):
                            val = float(val)
                        return round(val, ndigits)
                    except Exception:
                        return val

                cleaned_review = {
                    'recommendationid': review.get('recommendationid'),
                    'appid': review.get('appid'),
                    'voted_up': review.get('voted_up', False),
                    'recommendation': 'Positive' if review.get('voted_up', False) else 'Negative',
                    'author_steamid': author.get('steamid', '') if isinstance(author, dict) else '',
                    'author_num_games_owned': author.get('num_games_owned', 0) if isinstance(author, dict) else 0,
                    'author_num_reviews': author.get('num_reviews', 0) if isinstance(author, dict) else 0,
                    'playtime_forever_hours': safe_round(author.get('playtime_forever', 0) if isinstance(author, dict) else 0, 1),
                    'playtime_at_review_hours': safe_round(author.get('playtime_at_review', 0) if isinstance(author, dict) else 0, 1),
                    'review_text': review_text[:1000],
                    'review_word_count': word_count,
                    'review_char_count': char_count,
                    'language': review.get('language', ''),
                    'created_date': created_date,
                    'updated_date': updated_date,
                    'was_updated': updated_timestamp > created_timestamp,
                    'votes_up': review.get('votes_up', 0),
                    'votes_funny': review.get('votes_funny', 0),
                    'comment_count': review.get('comment_count', 0),
                    'weighted_vote_score': safe_round(review.get('weighted_vote_score', 0), 3),
                    'steam_purchase': review.get('steam_purchase', False),
                    'received_for_free': review.get('received_for_free', False),
                    'written_during_early_access': review.get('written_during_early_access', False),
                    'primarily_steam_deck': review.get('primarily_steam_deck', False),
                    'is_short_review': word_count < 10,
                    'is_long_review': word_count > 100,
                    'has_engagement': (review.get('votes_up', 0) + review.get('votes_funny', 0)) > 0,
                    'is_experienced_reviewer': (author.get('num_reviews', 0) if isinstance(author, dict) else 0) > 10,
                    'is_experienced_gamer': (author.get('num_games_owned', 0) if isinstance(author, dict) else 0) > 50
                }
                chunk_reviews.append(cleaned_review)
                if len(chunk_reviews) >= chunk_size:
                    df_chunk = pd.DataFrame(chunk_reviews)
                    df_chunk = df_chunk.drop_duplicates(subset=["recommendationid"])
                    cleaned_reviews.append(df_chunk)
                    chunk_reviews = []
            except Exception as e:
                print(f"⚠️ Erro processando linha {line_num}: {e}")
                logging.warning(f"Erro processando linha {line_num}: {e}")
                continue
    # Processa o último chunk
    if chunk_reviews:
        df_chunk = pd.DataFrame(chunk_reviews)
        df_chunk = df_chunk.drop_duplicates(subset=["recommendationid"])
        cleaned_reviews.append(df_chunk)
    if cleaned_reviews:
        df = pd.concat(cleaned_reviews, ignore_index=True)
        before = len(df)
        df = df.drop_duplicates(subset=["recommendationid"])
        after = len(df)
        # Seleciona colunas se especificado
        if columns:
            df = df[[col for col in columns if col in df.columns]]
        # Exporta no formato desejado
        if export_format == 'csv':
            df.to_csv(output_file, index=False)
        elif export_format == 'parquet':
            df.to_parquet(output_file, index=False)
        elif export_format == 'feather':
            df.to_feather(output_file)
        print(f"✅ {after} reviews limpos salvos em {output_file} (removidos {before-after} duplicados)")
        logging.info(f"{after} reviews limpos salvos em {output_file} (removidos {before-after} duplicados)")
    else:
        print("❌ Nenhum review válido encontrado")
        logging.error("Nenhum review válido encontrado")
    if error_lines:
        error_file = output_file.replace('.csv', '_errors.jsonl').replace('.parquet', '_errors.jsonl').replace('.feather', '_errors.jsonl')
        with open(error_file, 'w', encoding='utf-8') as ef:
            for err in error_lines:
                ef.write(json.dumps(err, ensure_ascii=False) + '\n')
        print(f"⚠️ {len(error_lines)} linhas problemáticas salvas em {error_file}")
        logging.warning(f"{len(error_lines)} linhas problemáticas salvas em {error_file}")

def main():
    parser = argparse.ArgumentParser(
        description="🧹 Limpeza e exportação dos dados do Steam scraper para análise",
        epilog="""
Exemplos de uso:
  python clean_data.py --games-format parquet --games-columns appid,name,genres
  python clean_data.py --reviews-format feather --reviews-columns recommendationid,review_text
  python clean_data.py --skip-reviews --games-format csv
  python clean_data.py --show-categories
  python clean_data.py --show-genres
""",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--games-input', default='data/json/game_details.jsonl',
        help='Arquivo JSONL de entrada dos jogos. Padrão: data/json/game_details.jsonl')
    parser.add_argument('--games-output', default='data/csv/games_clean.csv',
        help='Arquivo de saída dos jogos limpos. Padrão: data/csv/games_clean.csv. O formato depende de --games-format.')
    parser.add_argument('--reviews-input', default='data/json/game_reviews.jsonl',
        help='Arquivo JSONL de entrada dos reviews. Padrão: data/json/game_reviews.jsonl')
    parser.add_argument('--reviews-output', default='data/csv/reviews_clean.csv',
        help='Arquivo de saída dos reviews limpos. Padrão: data/csv/reviews_clean.csv. O formato depende de --reviews-format.')
    parser.add_argument('--games-columns', default=None,
        help='Colunas a manter nos jogos, separadas por vírgula. Exemplo: appid,name,genres')
    parser.add_argument('--reviews-columns', default=None,
        help='Colunas a manter nos reviews, separadas por vírgula. Exemplo: recommendationid,appid,review_text')
    parser.add_argument('--games-format', default='csv', choices=['csv','parquet','feather'],
        help='Formato de exportação dos jogos: csv, parquet ou feather. Padrão: csv')
    parser.add_argument('--reviews-format', default='csv', choices=['csv','parquet','feather'],
        help='Formato de exportação dos reviews: csv, parquet ou feather. Padrão: csv')
    parser.add_argument('--skip-games', action='store_true',
        help='Pula a limpeza dos jogos e processa apenas reviews')
    parser.add_argument('--skip-reviews', action='store_true',
        help='Pula a limpeza dos reviews e processa apenas jogos')
    parser.add_argument('--show-categories', action='store_true',
        help='Mostra todas as categorias encontradas nos dados de jogos e encerra')
    parser.add_argument('--show-genres', action='store_true',
        help='Mostra todos os gêneros encontrados nos dados de jogos e encerra')
    parser.add_argument('--log-file', default='logs/clean_data.log', help='Arquivo para salvar logs detalhados (padrão: logs/clean_data.log)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG','INFO','WARNING','ERROR'], help='Nível de log (DEBUG, INFO, WARNING, ERROR). Padrão: INFO')

    args = parser.parse_args()

    # Configura logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(args.log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    logging.info("Iniciando pipeline de limpeza Steam Harvest Data")

    # Garante que os diretórios de saída existem
    for out_path in [args.games_output, args.reviews_output]:
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

    # Opções de descoberta apenas
    if args.show_categories and os.path.exists(args.games_input):
        categories = discover_all_categories(args.games_input)
        print("\n📋 Categorias descobertas:")
        for cat_id, desc in sorted(categories.items()):
            print(f"  {cat_id}: {desc}")
        return None

    if args.show_genres and os.path.exists(args.games_input):
        genres = discover_all_genres(args.games_input)
        print("\n🎮 Gêneros descobertos:")
        for genre_id, desc in sorted(genres.items()):
            print(f"  {genre_id}: {desc}")
        return None

    print("🧹 Iniciando limpeza de dados do Steam...")

    # Limpa dados de jogos
    if not args.skip_games and os.path.exists(args.games_input):
        columns = args.games_columns.split(',') if args.games_columns else None
        clean_game_details(args.games_input, args.games_output, columns=columns, export_format=args.games_format)
    elif not args.skip_games:
        print(f"⚠️ Arquivo {args.games_input} não encontrado")

    # Limpa dados de reviews
    if not args.skip_reviews and os.path.exists(args.reviews_input):
        columns = args.reviews_columns.split(',') if args.reviews_columns else None
        clean_reviews(args.reviews_input, args.reviews_output, columns=columns, export_format=args.reviews_format)
    elif not args.skip_reviews:
        print(f"⚠️ Arquivo {args.reviews_input} não encontrado")

    print("✅ Limpeza concluída!")

    # Mostra estatísticas
    if os.path.exists(args.games_output):
        with open(args.games_output, 'r') as f:
            games_count = sum(1 for line in f) - 1  # -1 para o cabeçalho
        print(f"📊 Jogos limpos: {games_count}")

    if os.path.exists(args.reviews_output):
        with open(args.reviews_output, 'r') as f:
            reviews_count = sum(1 for line in f) - 1  # -1 para o cabeçalho
        print(f"📊 Reviews limpos: {reviews_count}")

if __name__ == "__main__":
    main()