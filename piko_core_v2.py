import hashlib
import json
import time
from flask import Flask, jsonify, request

class PikocoinL1:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.TOTAL_SUPPLY_CAP = 21000000
        self.BLOCK_REWARD = 50
        # 创建创世区块
        self.create_block(previous_hash="0", proof=100)

    def create_block(self, proof, previous_hash):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'transactions': self.pending_transactions,
            'proof': proof,
            'previous_hash': previous_hash,
        }
        self.pending_transactions = []
        self.chain.append(block)
        return block

    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        # 真正的 PoW 挖矿逻辑
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000" # 难度系数：4个0

# --- 启动本地 L1 节点服务 ---
app = Flask(__name__)
piko_chain = PikocoinL1()

@app.route('/mine', methods=['GET'])
def mine():
    last_block = piko_chain.last_block()
    last_proof = last_block['proof']
    # 开始工作量证明
    proof = piko_chain.proof_of_work(last_proof)
    
    previous_hash = hashlib.sha256(json.dumps(last_block, sort_keys=True).encode()).hexdigest()
    block = piko_chain.create_block(proof, previous_hash)
    
    response = {
        'message': "🎉 新块已铸造！",
        'index': block['index'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash']
    }
    return jsonify(response), 200

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': piko_chain.chain,
        'length': len(piko_chain.chain),
    }
    return jsonify(response), 200

if __name__ == '__main__':
    # 在 5000 端口启动你的本地 L1 节点
    app.run(host='0.0.0.0', port=5000)
