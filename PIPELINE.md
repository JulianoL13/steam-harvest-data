# Steam Harvest Data - Pipeline de Limpeza

Este pipeline realiza a limpeza, estruturação e exportação dos dados coletados do Steam scraper, facilitando análises e integrações.

## Instalação de dependências

Recomenda-se usar o gerenciador UV ou pip:

```sh
uv pip install -r requirements.txt
```

## Uso básico

```sh
python clean_data.py [opções]
```

### Exemplos

- Exportar jogos em Parquet, mantendo apenas algumas colunas:
  ```sh
  python clean_data.py --games-format parquet --games-columns appid,name,genres
  ```
- Exportar reviews em Feather, filtrando colunas:
  ```sh
  python clean_data.py --reviews-format feather --reviews-columns recommendationid,review_text
  ```
- Processar apenas jogos:
  ```sh
  python clean_data.py --skip-reviews
  ```
- Mostrar todas as categorias encontradas:
  ```sh
  python clean_data.py --show-categories
  ```

## Argumentos principais

- `--games-input`: Arquivo JSONL de entrada dos jogos (padrão: data/json/game_details.jsonl)
- `--games-output`: Arquivo de saída dos jogos limpos (padrão: data/csv/games_clean.csv)
- `--reviews-input`: Arquivo JSONL de entrada dos reviews (padrão: data/json/game_reviews.jsonl)
- `--reviews-output`: Arquivo de saída dos reviews limpos (padrão: data/csv/reviews_clean.csv)
- `--games-columns`: Colunas a manter nos jogos, separadas por vírgula (ex: appid,name,genres)
- `--reviews-columns`: Colunas a manter nos reviews, separadas por vírgula (ex: recommendationid,appid,review_text)
- `--games-format`: Formato de exportação dos jogos (csv, parquet, feather)
- `--reviews-format`: Formato de exportação dos reviews (csv, parquet, feather)
- `--skip-games`: Pula limpeza dos jogos
- `--skip-reviews`: Pula limpeza dos reviews
- `--show-categories`: Mostra todas as categorias encontradas e encerra
- `--show-genres`: Mostra todos os gêneros encontrados e encerra

## Funcionalidades

- Processamento eficiente em chunks para grandes volumes
- Remoção automática de duplicatas
- Logs detalhados e salvamento de linhas problemáticas
- Exportação flexível (csv, parquet, feather)
- Seleção de colunas para exportação
- Descoberta dinâmica de categorias e gêneros
- Criação automática de diretórios de saída

## Dicas
- Para integração com outros scripts, utilize os formatos Parquet ou Feather para maior performance.
- Consulte o help completo com:
  ```sh
  python clean_data.py --help
  ```

## Requisitos
- Python 3.8+
- pandas
- tqdm

---

Para dúvidas ou sugestões, consulte o README ou abra uma issue.
