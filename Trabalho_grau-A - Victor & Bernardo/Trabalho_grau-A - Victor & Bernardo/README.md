# Sincronização de arquivos P2P com UDP

Trabalho I — Redes de Computadores: Aplicação e Transporte (Unisinos)
Grupo: Bernardo Lazzari, Victor Mingues Heinzmann e Bernardo Marinho Lazzari

Cada peer mantém a pasta `tmp` igual em todas as máquinas. Se um arquivo for
adicionado em um peer, ele aparece nos outros. Se for apagado, some de todos.

## Como rodar

Precisa só de Python 3.

**No mesmo computador** (3 terminais):

```
python peer.py 127.0.0.1:5001 tmpA
python peer.py 127.0.0.1:5002 tmpB
python peer.py 127.0.0.1:5003 tmpC
```

**Em máquinas diferentes:** coloque os IPs no `peers.json` (o mesmo arquivo em
todas) e rode em cada máquina com o próprio IP:

```
python peer.py 192.168.0.10:5000
```

**Novo peer:** inicie um quarto peer com a pasta vazia. Ele recebe todos os
arquivos sozinho.

```
python peer.py 127.0.0.1:5004 tmpD
```

## Como funciona

Cada peer usa um único socket UDP: uma thread recebe mensagens (servidor) e o
laço principal vigia a pasta e avisa os outros (cliente).

| Mensagem | Significado |
|---|---|
| `ANUNCIO` | tenho um arquivo novo |
| `REMOVIDO` | apaguei um arquivo |
| `LISTA` | me mande a sua lista de arquivos |
| `OI` | estou ativo, e estes são os meus arquivos (enviado a cada 1 s) |
| `PEDIR` | me mande pedaços de um arquivo |
| `DADOS` | um pedaço do arquivo |

Como o UDP pode perder pacotes, os avisos são enviados 3 vezes, o `OI` vai a
cada segundo e os pedaços de arquivo que não chegam são pedidos de novo.

A tela de cada peer mostra os peers ativos, os arquivos de cada um e se a rede
está sincronizada.
