import requests
import time

# ⚠️ 这里非常关键：
# 请从你刚才执行 modal deploy 的返回信息中找到两个 URL
# 将它们完整地填入下面的引号里
GET_URL = "你的地址.modal.run"
POST_URL = "你的地址block.modal.run"

MY_ADDRESS = "yay37_pioneer" # 你的创始人地址

def start_mining():
    print(f"⛏️  Pikocoin 矿工正在你的 i5-4590 上启动...")
    
    while True:
        # 生成一个模拟的算力证明
        proof = f"piko_pow_{int(time.time())}_yay37"
        
        try:
            # 向云端请求加钱
            response = requests.post(POST_URL, json={
                "address": MY_ADDRESS,
                "proof": proof
            })
            data = response.json()
            
            if data.get("status") == "success":
                print(f"💰 挖矿成功！余额现为: {data['new_balance']} PIKO")
            else:
                print("❌ 提交失败，请检查网络。")
                
        except Exception as e:
            print(f"⚠️ 无法连接到主网: {e}")
            
        time.sleep(10) # 每 10 秒挖一次

if __name__ == "__main__":
    start_mining()
