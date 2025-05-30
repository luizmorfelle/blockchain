import json
import os
import time 
from typing import List, Dict, Callable

from block import Block, create_block, create_block_from_dict, create_genesis_block
from network import broadcast_chain, broadcast_transaction, is_chain_valid 


def load_chain(fpath: str) -> List[Block]:
    if os.path.exists(fpath):
        try:
            with open(fpath) as f:
                data = json.load(f)
                blockchain = []
                for block_data in data:
                    block = create_block_from_dict(block_data)
                    blockchain.append(block)
                print(f"[i] Loaded chain from {fpath} with {len(blockchain)} blocks.")
                return blockchain
        except (json.JSONDecodeError, IOError) as e:
            print(f"[!] Error loading chain from {fpath}: {e}. Starting fresh.")
            return [create_genesis_block()]

    return [create_genesis_block()]


def save_chain(fpath: str, chain: list[Block]):
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    blockchain_serializable = []
    for b in chain:
        blockchain_serializable.append(b.as_dict())

    try:
        with open(fpath, "w") as f:
            json.dump(blockchain_serializable, f, indent=2)
        print(f"[i] Chain saved to {fpath}")
    except IOError as e:
        print(f"[!] Error saving chain to {fpath}: {e}")


def print_chain(blockchain: List[Block]):
    print("--- Current Blockchain State ---")
    if not blockchain:
        print("(empty)")
        return
    for b in blockchain:
        print(f"  Index: {b.index}, Hash: {b.hash[:10]}..., PrevHash: {b.prev_hash[:10]}..., Nonce: {b.nonce}, Tx: {len(b.transactions)}")
    print("------------------------------")

def mine_block(
    transactions: List[Dict],
    blockchain: List[Block],
    node_id: str,
    reward: int,
    difficulty: int,
    blockchain_fpath: str,
    peers_fpath: str,
):
    print(f"\n[⛏️] Node {node_id} starting mining for block {len(blockchain)}...")
    block_transactions = list(transactions) 
    
    new_block = create_block(
        block_transactions, 
        blockchain[-1].hash,
        miner=node_id,
        index=len(blockchain),
        reward=reward,
        difficulty=difficulty,
    )
    
    blockchain.append(new_block)
    transactions.clear() 
    save_chain(blockchain_fpath, blockchain)
    
    broadcast_chain(blockchain, peers_fpath)
    
    print(f"[✓] Node {node_id} mined block {new_block.index} and broadcasted the updated chain.")
    print_chain(blockchain) 


def make_transaction(sender, recipient, amount, transactions, peers_fpath):
    try:
        amount_float = float(amount)
        if amount_float <= 0:
            print("[!] Transaction amount must be positive.")
            return
    except ValueError:
        print("[!] Invalid amount format.")
        return
        
    tx = {"from": sender, "to": recipient, "amount": amount} 
    transactions.append(tx)
    broadcast_transaction(tx, peers_fpath)
    print(f"[+] Transaction {sender} -> {recipient} ({amount}) added to mempool and broadcasted.")


def get_balance(node_id: str, blockchain: List[Block]) -> float:
    balance = 0.0
    for block in blockchain:
        for tx in block.transactions:
            try:
                tx_amount = float(tx["amount"])
                if tx["to"] == node_id:
                    balance += tx_amount
                if tx["from"] == node_id:
                    balance -= tx_amount
            except (ValueError, KeyError):
                print(f"[!] Skipping invalid transaction format in balance calculation: {tx}")
                continue 
    return balance

def on_valid_block_callback(fpath, chain):
    save_chain(fpath, chain)

