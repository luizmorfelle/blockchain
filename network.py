# network.py modified with longest chain rule (broadcast full chain approach)
import json
import os
import socket
import threading
import traceback
from typing import Callable, Dict, List
from block import Block, create_block_from_dict, hash_block

def is_chain_valid(chain: List[Block], difficulty: int) -> bool:
    if not chain:
        print("[!] Chain validation failed: Chain is empty.")
        return False
    
    if chain[0].index != 0 or chain[0].prev_hash != "0" or chain[0].hash != "0":
        print(f"[!] Chain validation failed: Genesis block invalid: {chain[0].as_dict()}")
        pass

    for i in range(1, len(chain)):
        current_block = chain[i]
        previous_block = chain[i-1]

        if current_block.prev_hash != previous_block.hash:
            print(f"[!] Chain validation failed: Block {i} prev_hash ({current_block.prev_hash[:10]}...) mismatch with block {i-1} hash ({previous_block.hash[:10]}...).")
            return False
        expected_hash = hash_block(current_block) 
        if current_block.hash != expected_hash:
             print(f"[!] Chain validation failed: Block {i} hash is invalid. Expected {expected_hash[:10]}..., got {current_block.hash[:10]}...")
             return False
        if not current_block.hash.startswith("0" * difficulty):
             print(f"[!] Chain validation failed: Block {i} PoW not satisfied (hash: {current_block.hash[:10]}...).")
             return False

    print("[✓] Received chain passed validation.")
    return True

def list_peers(fpath: str):
    if not os.path.exists(fpath):
        print("[!] No peers file founded!")
        return []
    with open(fpath) as f:
        peers_addr = []
        for line in f: 
            line = line.strip()
            if line:
                try:
                    host, port_str = line.split(':')
                    peers_addr.append((host, int(port_str)))
                except ValueError:
                    print(f"[!] Skipping invalid peer entry: {line}")
        return peers_addr

def broadcast_single_block(block: Block, peers_fpath: str, port: int):
    print(f"Broadcasting single block {block.index}...")
    peers = list_peers(peers_fpath)
    print(f"Peers to broadcast to: {peers}")
    for peer_host, peer_port in peers:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2) 
            s.connect((peer_host, peer_port))
            s.send(json.dumps({"type": "block", "data": block.as_dict()}).encode())
            s.close()
            print(f"Sent block {block.index} to {peer_host}:{peer_port}")
        except Exception as e:
            print(f"[!] Failed to send block to {peer_host}:{peer_port}. Error: {e}")
            pass

def broadcast_chain(chain: List[Block], peers_fpath: str):
    print(f"Broadcasting full chain (length {len(chain)})...")
    peers = list_peers(peers_fpath)
    print(f"Peers to broadcast to: {peers}")
    chain_data = [b.as_dict() for b in chain]
    message = json.dumps({"type": "full_chain", "data": chain_data}).encode()
    for peer_host, peer_port in peers:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2) 
            s.connect((peer_host, peer_port))
            s.send(message)
            s.close()
            print(f"Sent full chain to {peer_host}:{peer_port}")
        except Exception as e:
            print(f"[!] Failed to send full chain to {peer_host}:{peer_port}. Error: {e}")
            pass

def broadcast_transaction(tx: Dict, peers_fpath: str):
    print("Broadcasting transaction...")
    peers = list_peers(peers_fpath)
    print(f"Peers to broadcast to: {peers}")
    message = json.dumps({"type": "tx", "data": tx}).encode()
    for peer_host, peer_port in peers:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2) 
            s.connect((peer_host, peer_port))
            s.send(message)
            s.close()
            print(f"Sent tx to {peer_host}:{peer_port}")
        except Exception as e:
            print(
                f"[!] Failed to send tx to {peer_host}:{peer_port}. Error: {e}"
            )

def handle_client(
    conn: socket.socket,
    addr: tuple, 
    blockchain: List[Block],
    difficulty: int,
    transactions: List[Dict],
    blockchain_fpath: str,
    peers_fpath: str, 
    on_valid_block_callback: Callable,
):
    try:
        data = conn.recv(65536).decode() 
        if not data:
            print(f"[!] Received empty data from {addr}. Closing connection.")
            conn.close()
            return
            
        msg = json.loads(data)
        msg_type = msg.get("type")
        msg_data = msg.get("data")

        print(f"[NETWORK] Received message type ", msg_type, " from ", addr)

        if msg_type == "full_chain":
            received_chain_data = msg_data
            if not isinstance(received_chain_data, list):
                 print(f"[!] Invalid chain data received from {addr}. Expected list.")
                 conn.close()
                 return
                 
            print(f"Received full chain of length {len(received_chain_data)} from {addr}")
            try:
                received_blockchain = [create_block_from_dict(b) for b in received_chain_data]
            except Exception as e:
                print(f"[!] Error deserializing chain from {addr}: {e}")
                conn.close()
                return

            if is_chain_valid(received_blockchain, difficulty):
                if len(received_blockchain) > len(blockchain):
                    print(f"[✓] Received valid longer chain (length {len(received_blockchain)}) from {addr}. Replacing local chain (length {len(blockchain)})." )
                    blockchain[:] = received_blockchain 
                    on_valid_block_callback(blockchain_fpath, blockchain)
                else:
                    print(f"[i] Received valid chain from {addr}, but it's not longer than local chain ({len(received_blockchain)} <= {len(blockchain)}). Ignoring.")
            else:
                print(f"[!] Received chain from {addr} failed validation. Ignoring.")

        elif msg_type == "tx":
            tx = msg_data
            if isinstance(tx, dict) and all(k in tx for k in ["from", "to", "amount"]):
                if tx not in transactions:
                    transactions.append(tx)
                    print(f"[+] Transaction received from {addr} and added to mempool.")
                    broadcast_transaction(tx, peers_fpath)
                else:
                    print(f"[i] Duplicate transaction received from {addr}. Ignoring.")
            else:
                 print(f"[!] Invalid transaction format received from {addr}. Ignoring.")


        else:
            print(f"[!] Received unknown message type '{msg_type}' from {addr}. Ignoring.")

    except json.JSONDecodeError:
        print(f"[!] Received invalid JSON from {addr}. Data: {data[:100]}...")
    except socket.timeout:
        print(f"[!] Socket timeout receiving data from {addr}.")
    except Exception as e:
        print(
            f"Exception when handling client {addr}. Exception: {e}. {traceback.format_exc()}"
        )
    finally:
        conn.close()

def start_server(
    host: str,
    port: int,
    blockchain: List[Block],
    difficulty: int,
    transactions: List[Dict],
    blockchain_fpath: str,
    peers_fpath: str, 
    on_valid_block_callback: Callable,
):
    def server_thread():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
        try:
            server.bind((host, port))
            server.listen()
            print(f"[SERVER] Listening on {host}:{port}")
        except OSError as e:
            print(f"[!!!] SERVER BIND FAILED for {host}:{port}. Error: {e}")
            print("Exiting server thread.")
            return 
            
        while True:
            try:
                conn, addr = server.accept()
                print(f"[SERVER] Accepted connection from {addr}")
                threading.Thread(
                    target=handle_client,
                    args=(
                        conn,
                        addr,
                        blockchain,
                        difficulty,
                        transactions,
                        blockchain_fpath,
                        peers_fpath,
                        on_valid_block_callback,
                    ),
                    daemon=True
                ).start()
            except Exception as e:
                 print(f"[!!!] SERVER ACCEPT FAILED. Error: {e}")

    threading.Thread(target=server_thread, daemon=True).start()

