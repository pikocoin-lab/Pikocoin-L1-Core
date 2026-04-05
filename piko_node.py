import modal
import hashlib
import time

# 1. 定义云端工厂环境（已集成你刚才下载的所有依赖包）
image = modal.Image.debian_slim().pip_install(
    "cryptography", 
    "fastapi", 
    "pydantic"
)

# 2. 创建 Pikocoin 核心 App
app = modal.App("pikocoin-l1-core")

# 3. 挂载云端账本 (持久化存储)
ledger = modal.Dict.from_name("piko-ledger", create_if_missing=True)

# --- 接口一：查询钱包余额 (GET) ---
@app.function(image=image)
@modal.fastapi_endpoint(method="GET")
def get_balance(address: str):
    balance = ledger.get(address, 0)
    return {
        "address": address, 
        "balance": f"{balance} PIKO",
        "status": "Online"
    }

# --- 接口二：矿工提交 AI 算力证明 (POST) ---
@app.function(image=image)
@modal.fastapi_endpoint(method="POST")
def mine_block(payload: dict):
    miner_addr = payload.get("address")
    proof = payload.get("proof")
    
    # 简单的 AI 算力有效性模拟检查
    if proof and len(proof) > 10:
        current_bal = ledger.get(miner_addr, 0)
        new_bal = current_bal + 50  # 每一个块奖励 50 枚
        ledger[miner_addr] = new_bal
        
        return {
            "status": "success", 
            "reward": 50, 
            "new_balance": new_bal
        }
    
    return {"status": "fail", "reason": "Proof too weak"}

@app.local_entrypoint()
def main():
    print("🚀 Pikocoin L1 核心节点启动成功！")
