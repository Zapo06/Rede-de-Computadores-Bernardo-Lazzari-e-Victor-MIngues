import base64
import json
import os
import socket
import sys
import threading
import time

PARTE = 8000  # bytes de arquivo por datagrama


def endereco(texto):
    ip, porta = texto.split(":")
    return (ip, int(porta))


eu = endereco(sys.argv[1])
pasta = sys.argv[2] if len(sys.argv) > 2 else "tmp"
os.makedirs(pasta, exist_ok=True)
with open("peers.json") as f:
    peers = {endereco(p) for p in json.load(f)["peers"]} - {eu}

meus = set()       
removidos = set()  
baixando = {}     
vistos = {}        
eventos = []
trava = threading.Lock()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
if hasattr(socket, "SIO_UDP_CONNRESET"):  
    sock.ioctl(socket.SIO_UDP_CONNRESET, False)
sock.bind(("0.0.0.0", eu[1]))


def log(texto):
    eventos.append(time.strftime("%H:%M:%S  ") + texto)
    del eventos[:-6]


def enviar(msg, destino):
    try:
        sock.sendto(json.dumps(msg).encode(), destino)
    except OSError:
        pass


def enviar_todos(msg):
    for p in list(peers):
        enviar(msg, p)


def arquivos_da_pasta():
    return {n for n in os.listdir(pasta)
            if os.path.isfile(os.path.join(pasta, n)) and not n.endswith(".parte")}


def pedir(nome):
    d = baixando[nome]
    if d["total"] is None:
        enviar({"tipo": "PEDIR", "nome": nome}, d["de"])
    else:
        faltam = [i for i in range(d["total"]) if i not in d["partes"]]
        enviar({"tipo": "PEDIR", "nome": nome, "partes": faltam}, d["de"])



def servidor():
    while True:
        try:
            dados, de = sock.recvfrom(65535)
            msg = json.loads(dados)
        except (OSError, ValueError):
            continue
        with trava:
            try:
                tratar(msg, de)
            except (KeyError, TypeError, OSError):
                pass  


def tratar(msg, de):
    if de not in peers:
        peers.add(de)
        log(f"* novo peer: {de[0]}:{de[1]}")
    tipo = msg["tipo"]
    nome = os.path.basename(msg.get("nome", ""))
    caminho = os.path.join(pasta, nome)

    if tipo == "LISTA":  
        enviar({"tipo": "OI", "arquivos": sorted(meus)}, de)

    elif tipo == "OI":  
        vistos[de] = (time.time(), msg["arquivos"])
        for n in msg["arquivos"]:
            if n in removidos:
                enviar({"tipo": "REMOVIDO", "nome": n}, de)  
            elif n in baixando:
                baixando[n]["de"] = de
            elif n not in meus:
                baixando[n] = {"de": de, "total": None, "partes": {}}
                log(f"v baixando: {n}")
                pedir(n)

    elif tipo == "ANUNCIO":  
        removidos.discard(nome)
        if nome not in meus and nome not in baixando:
            baixando[nome] = {"de": de, "total": None, "partes": {}}
            log(f"v baixando: {nome}")
            pedir(nome)

    elif tipo == "REMOVIDO":  
        removidos.add(nome)
        baixando.pop(nome, None)
        if nome in meus:
            meus.discard(nome)
            if os.path.exists(caminho):
                os.remove(caminho)
            log(f"- removido pela rede: {nome}")

    elif tipo == "PEDIR":  
        if nome not in meus:
            return
        with open(caminho, "rb") as f:
            conteudo = f.read()
        total = max(1, -(-len(conteudo) // PARTE))
        for i in msg.get("partes") or range(total):
            pedaco = conteudo[i * PARTE:(i + 1) * PARTE]
            enviar({"tipo": "DADOS", "nome": nome, "parte": i, "total": total,
                    "dados": base64.b64encode(pedaco).decode()}, de)

    elif tipo == "DADOS":  
        d = baixando.get(nome)
        if not d:
            return
        if d["total"] != msg["total"]:
            d["total"], d["partes"] = msg["total"], {}
        d["partes"][msg["parte"]] = base64.b64decode(msg["dados"])
        if len(d["partes"]) == d["total"]:  
            with open(caminho + ".parte", "wb") as f:
                for i in range(d["total"]):
                    f.write(d["partes"][i])
            os.replace(caminho + ".parte", caminho)
            meus.add(nome)
            del baixando[nome]
            log(f"+ recebido: {nome}")


def cliente():
    with trava:
        atual = arquivos_da_pasta()
        for n in atual - meus - set(baixando):  
            meus.add(n)
            removidos.discard(n)
            log(f"+ arquivo novo: {n}")
            for _ in range(3):  
                enviar_todos({"tipo": "ANUNCIO", "nome": n})
        for n in meus - atual:  
            meus.discard(n)
            removidos.add(n)
            log(f"- apagado: {n}")
            for _ in range(3):
                enviar_todos({"tipo": "REMOVIDO", "nome": n})

        enviar_todos({"tipo": "OI", "arquivos": sorted(meus)})
        for n in baixando: 
            pedir(n)


def tela():
    def linha(nome, status, arqs):
        lista = ", ".join(arqs)
        lista = lista if len(lista) <= 40 else lista[:37] + "..."
        return f"{nome:<24}{status:<10}{len(arqs):>3}  {lista}"

    with trava:
        linhas = [f"=== PEER {eu[0]}:{eu[1]}  |  pasta: {pasta}  |  Ctrl+C sai ===", "",
                  f"{'PEER':<24}{'STATUS':<10}QTD  ARQUIVOS",
                  linha(f"{eu[0]}:{eu[1]} (eu)", "ativo", sorted(meus))]
        sincronizado = not baixando
        for p in sorted(peers):
            hora, arqs = vistos.get(p, (0, []))
            if time.time() - hora < 5:
                linhas.append(linha(f"{p[0]}:{p[1]}", "ativo", arqs))
                sincronizado = sincronizado and arqs == sorted(meus)
            else:
                linhas.append(linha(f"{p[0]}:{p[1]}", "INATIVO", []))
        linhas += ["", f"Rede sincronizada: {'SIM' if sincronizado else 'NAO'}",
                   "", f"LISTA DE ARQUIVOS DO SISTEMA ({len(meus)}):"]
        for n in sorted(meus):
            tamanho = os.path.getsize(os.path.join(pasta, n)) if os.path.exists(os.path.join(pasta, n)) else 0
            linhas.append(f"  {n:<40}{tamanho:>10} bytes")
        linhas += ["", "ULTIMOS EVENTOS:"] + ["  " + e for e in eventos]
    print("\033[H\033[J" + "\n".join(linhas), flush=True)

os.system("")              
meus = arquivos_da_pasta() 
threading.Thread(target=servidor, daemon=True).start()
enviar_todos({"tipo": "LISTA"})  
try:
    while True:
        cliente()
        tela()
        time.sleep(1)
except KeyboardInterrupt:
    print("\nPeer encerrado.")
