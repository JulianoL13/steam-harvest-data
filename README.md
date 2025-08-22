# 🎮 Steam Data Harvester

Um scraper robusto e otimizado para coletar dados de jogos da Steam usando proxies rotativos, processamento paralelo e tolerância a falhas.

## 📋 Índice

- [Características](#-características)
- [Instalação](#-instalação)
- [Uso Básico](#-uso-básico)
- [Configuração de Proxies](#-configuração-de-proxies)
- [Modos de Operação](#-modos-de-operação)
- [Parâmetros](#-parâmetros)
- [Exemplos](#-exemplos)
- [Arquivos de Saída](#-arquivos-de-saída)
- [Logs e Monitoramento](#-logs-e-monitoramento)
- [Tolerância a Falhas](#-tolerância-a-falhas)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Contribuindo](#-contribuindo)

## ✨ Características

- **🚀 Processamento Paralelo**: Utiliza múltiplas threads para maximizar eficiência
- **🔄 Rotação de Proxies**: Suporte automático a múltiplos proxies com fallback
- **💾 Tolerância a Falhas**: Sistema de cursor para retomar execução após interrupções
- **📊 Monitoramento**: Logs detalhados com progresso e estatísticas
- **🎯 Controle Preciso**: Limite exato de jogos coletados (evita overrun)
- **📝 Validação**: Filtragem automática de jogos válidos vs DLCs/apps não-jogo
- **⚡ Otimizado**: Rate limiting inteligente e retry com backoff exponencial
- **🔒 Thread-Safe**: Operações seguras em ambiente multi-threaded

## 📦 Instalação

### Dependências

```bash
pip install requests
```

### Clone/Download

```bash
git clone <seu-repositorio>
cd steam-harvest-data
```

ou simplesmente baixe o arquivo `scrapper.py`.

## 🚀 Uso Básico

### Comando Simples (Modo Sequencial)

```bash
python scrapper.py --max_games 10 --max_reviews 5
```

### Modo Paralelo (Recomendado)

```bash
python scrapper.py --parallel --workers 8 --max_games 50 --max_reviews 10
```

### Com Proxies

```bash
python scrapper.py --parallel --workers 5 --proxies proxies.txt --max_games 100
```

## 🌐 Configuração de Proxies

Crie um arquivo `proxies.txt` com seus proxies:

```
# Formato: um proxy por linha ou separados por vírgula
proxy1.example.com:8080
proxy2.example.com:3128
username:password@proxy3.example.com:8080

# Ou em uma linha separados por vírgula:
proxy1.com:8080,proxy2.com:3128,proxy3.com:8080
```

**Formatos Suportados:**
- `proxy.com:8080`
- `http://proxy.com:8080`
- `https://proxy.com:8080`
- `username:password@proxy.com:8080`

O script automaticamente adiciona `https://` se não especificado.

## 🔧 Modos de Operação

### Modo Sequencial
- Usa apenas IP local
- Processamento um jogo por vez
- Mais lento, mas mais conservador
- Ideal para testes ou uso casual

### Modo Paralelo
- Utiliza múltiplas threads
- Rotação automática de proxies
- Processamento otimizado
- **Recomendado para coleta em larga escala**

## ⚙️ Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `--max_games` | int | 10 | Número máximo de jogos válidos a coletar |
| `--max_reviews` | int | 10 | Reviews por jogo (0 = sem reviews) |
| `--parallel` | flag | False | Ativa modo paralelo |
| `--workers` | int | 8 | Número de threads (modo paralelo) |
| `--proxies` | str | None | Arquivo com lista de proxies |
| `--batch_size` | int | 200 | Tamanho do lote para processamento |
| `--cursor_file` | str | scraper_cursor.txt | Arquivo de cursor para retomada |
| `--reset_cursor` | flag | False | Ignora cursor e recomeça do zero |
| `--game_details_file` | str | game_details.jsonl | Arquivo de saída dos detalhes |
| `--game_reviews_file` | str | game_reviews.jsonl | Arquivo de saída das reviews |
| `--checkpoint_interval` | int | 25 | Intervalo para salvar progresso |

## 📝 Exemplos

### Coleta Rápida (Poucos Jogos)
```bash
# 20 jogos, 3 reviews cada, modo paralelo
python scrapper.py --parallel --max_games 20 --max_reviews 3 --workers 4
```

### Coleta em Larga Escala
```bash
# 500 jogos com proxies, 10 reviews cada
python scrapper.py --parallel --workers 10 --proxies proxies.txt --max_games 500 --max_reviews 10
```

### Coleta Apenas Detalhes (Sem Reviews)
```bash
# Coleta apenas informações dos jogos, sem reviews
python scrapper.py --parallel --max_games 100 --max_reviews 0
```

### Retomar Execução Interrompida
```bash
# Continua de onde parou (usa cursor automático)
python scrapper.py --parallel --max_games 200
```

### Recomeçar do Zero
```bash
# Ignora progresso anterior e recomeça
python scrapper.py --reset_cursor --max_games 50
```

## 📁 Arquivos de Saída

### game_details.jsonl
Contém detalhes completos dos jogos em formato JSONL:

```json
{
  "appid": 570,
  "name": "Dota 2",
  "type": "game",
  "steam_appid": 570,
  "required_age": 0,
  "is_free": true,
  "detailed_description": "...",
  "short_description": "...",
  "header_image": "https://...",
  "website": "http://...",
  "developers": ["Valve"],
  "publishers": ["Valve"],
  "price_overview": {...},
  "categories": [...],
  "genres": [...],
  "screenshots": [...],
  "release_date": {...}
}
```

### game_reviews.jsonl
Contém reviews dos jogos:

```json
{
  "appid": 570,
  "recommendationid": "123456789",
  "author": {
    "steamid": "...",
    "num_games_owned": 150,
    "num_reviews": 5,
    "playtime_forever": 1200,
    "playtime_last_two_weeks": 50
  },
  "language": "english",
  "review": "Great game! Highly recommended...",
  "timestamp_created": 1692661200,
  "timestamp_updated": 1692661200,
  "voted_up": true,
  "votes_up": 25,
  "votes_funny": 2,
  "comment_count": 3
}
```

## 📊 Logs e Monitoramento

### Logs no Console
```
2025-08-22 10:30:15 - MainThread - INFO - 🚀 INICIANDO Steam Scraper Otimizado
2025-08-22 10:30:15 - MainThread - INFO - 🎯 Meta: 50 jogos | Reviews: 10 por jogo
2025-08-22 10:30:15 - MainThread - INFO - 📡 Carregados 5 proxies válidos
2025-08-22 10:30:16 - MainThread - INFO - 📦 125000 jogos obtidos da Steam API
2025-08-22 10:30:20 - ThreadPoolExecutor-0_1 - INFO - 🎮 JOGO VÁLIDO: 730 - Counter-Strike 2
2025-08-22 10:30:21 - ThreadPoolExecutor-0_2 - INFO - 📝 10 reviews salvos para 730
2025-08-22 10:30:22 - MainThread - INFO - 📈 Progresso paralelo: 15/50
```

### Arquivo de Log
Além do console, logs são salvos em `steam_scraper.log` para análise posterior.

### Monitoramento de Progresso
- **ETA**: Estimativa de tempo restante baseada na taxa atual
- **Taxa**: Jogos processados por minuto
- **Progresso**: Contagem atual vs meta
- **Status de Proxies**: Proxies funcionais vs falhados

## 🔄 Tolerância a Falhas

### Sistema de Cursor
- **Automático**: Salva progresso a cada N jogos processados
- **Recuperação**: Retoma automaticamente do último ponto salvo
- **Proteção**: Evita reprocessar jogos já coletados

### Arquivos de Estado
- `scraper_cursor.txt.progress`: Estado completo (JSON)
- `scraper_cursor.txt.backup`: Backup automático
- `steam_scraper.log`: Log histórico

### Recuperação de Proxies
- **Rotação Automática**: Troca proxy em caso de falha
- **Fallback para IP Local**: Continua funcionando sem proxies
- **Rate Limiting**: Respeita limites da Steam API

### Interrupção Graceful
- **Ctrl+C**: Salva estado e finaliza limpo
- **Meta Atingida**: Para imediatamente ao atingir --max_games
- **Timeout**: Evita travamentos em requests lentas

## 📁 Estrutura do Projeto

```
steam-harvest-data/
├── scrapper.py              # Script principal
├── README.md               # Esta documentação
├── proxies.txt             # Lista de proxies (você cria)
├── game_details.jsonl      # Saída: detalhes dos jogos
├── game_reviews.jsonl      # Saída: reviews dos jogos
├── scraper_cursor.txt.progress  # Estado do cursor
├── scraper_cursor.txt.backup    # Backup do cursor
└── steam_scraper.log       # Logs detalhados
```

## 🛠️ Configuração Avançada

### Otimização de Performance

```bash
# Para máxima velocidade (requer proxies robustos)
python scrapper.py \
    --parallel \
    --workers 15 \
    --batch_size 500 \
    --checkpoint_interval 50 \
    --proxies proxies.txt \
    --max_games 1000
```

### Configuração Conservadora

```bash
# Para evitar rate limits (mais lento, mais seguro)
python scrapper.py \
    --parallel \
    --workers 3 \
    --batch_size 100 \
    --checkpoint_interval 10 \
    --max_games 200
```

### Modo Debug

Para desenvolvimento ou debug, modifique o nível de log no código:

```python
logging.basicConfig(level=logging.DEBUG)  # Mais detalhes
```

## ⚠️ Limitações e Considerações

### Rate Limits
- A Steam API tem limites de rate
- Use proxies para aumentar throughput
- O script implementa backoff automático

### Qualidade dos Dados
- Apenas jogos válidos (não DLCs)
- Filtragem automática de apps inválidos
- Validação de dados JSON

### Recursos do Sistema
- Modo paralelo usa mais CPU e memória
- Ajuste `--workers` conforme sua máquina
- Monitorar uso de rede com proxies

## 🐛 Solução de Problemas

### Script não finaliza
- Verifique se não há proxies lentos/travados
- Reduza `--workers` se sistema sobrecarregado
- Use Ctrl+C para interrupção graceful

### Poucos jogos encontrados
- Lista da Steam contém muitos apps não-jogo
- Normal encontrar ~5-10% de jogos válidos
- Aumente `--max_games` se necessário

### Erros de proxy
- Verifique formato do arquivo `proxies.txt`
- Teste proxies manualmente
- Script continua com IP local se proxies falharem

### Arquivo corrompido
- O script usa backups automáticos
- Delete arquivos de estado para recomeçar
- Use `--reset_cursor` para forçar reset

## 📈 Estatísticas de Performance

### Benchmarks Típicos
- **Sem Proxies**: ~10-20 jogos/minuto
- **Com 5 Proxies**: ~50-100 jogos/minuto  
- **10+ Proxies**: ~100-200 jogos/minuto

### Fatores que Afetam Performance
- Qualidade e velocidade dos proxies
- Número de workers
- Quantidade de reviews por jogo
- Rate limits da Steam

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## 📄 Licença

Este projeto é disponibilizado "como está" para fins educacionais e de pesquisa. Use responsavelmente e respeite os termos de serviço da Steam.

## ⚡ Quick Start

```bash
# 1. Instalar dependências
pip install requests

# 2. Coleta básica (10 jogos)
python scrapper.py --parallel --max_games 10

# 3. Com proxies (se disponível)
echo "proxy1.com:8080,proxy2.com:8080" > proxies.txt
python scrapper.py --parallel --proxies proxies.txt --max_games 50

# 4. Verificar resultados
wc -l game_details.jsonl
head -1 game_details.jsonl | python -m json.tool
```

---

**🎮 Happy Scraping!** 

Para dúvidas ou problemas, abra uma issue no repositório.
